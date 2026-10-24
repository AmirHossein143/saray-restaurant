import json

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from reservations.models import Reservation
from saray_menu.models import Category, MenuItem, MenuItemVariant, SiteSettings

User = get_user_model()


class StudioBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pw-12345-xyz')
        cls.staff = User.objects.create_user('clerk', password='pw-12345-xyz', is_staff=True)

    def setUp(self):
        self.client.force_login(self.admin)

    def url(self, name, *args):
        return reverse(f'studio:{name}', args=args)

    def post_json(self, url, payload, method='post'):
        return getattr(self.client, method)(url, json.dumps(payload), content_type='application/json')


class AccessTests(StudioBase):
    def test_anonymous_is_redirected_to_login(self):
        response = Client().get('/studio/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_anonymous_api_gets_401(self):
        self.assertEqual(Client().get(self.url('tables')).status_code, 401)

    def test_staff_without_superuser_is_forbidden(self):
        client = Client()
        client.force_login(self.staff)
        self.assertEqual(client.get('/studio/').status_code, 403)
        self.assertEqual(client.get(self.url('tables')).status_code, 403)
        response = client.delete(self.url('row', 'saray_menu.category', 1))
        self.assertEqual(response.status_code, 403)

    def test_superuser_sees_the_app(self):
        response = self.client.get('/studio/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Data Studio')
        self.assertIn('csrftoken', response.cookies)

    def test_writes_require_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        item = MenuItem.objects.first()
        response = client.delete(self.url('row', 'saray_menu.menuitem', item.pk))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(MenuItem.objects.filter(pk=item.pk).exists())


class SchemaTests(StudioBase):
    def test_tables_listing(self):
        data = self.client.get(self.url('tables')).json()
        by_key = {t['key']: t for t in data['tables']}
        self.assertEqual(by_key['saray_menu.menuitem']['count'], 78)
        self.assertEqual(by_key['saray_menu.category']['count'], 9)
        self.assertTrue(by_key['auth.user']['readonly'])
        self.assertFalse(by_key['saray_menu.sitesettings']['can_delete'])
        self.assertNotIn('sessions.session', by_key)

    def test_password_hash_is_never_exposed(self):
        data = self.client.get(self.url('tables')).json()
        user = next(t for t in data['tables'] if t['key'] == 'auth.user')
        self.assertNotIn('password', [f['name'] for f in user['fields']])
        rows = self.client.get(self.url('rows', 'auth.user')).json()['rows']
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn('password', row['v'])
        self.assertNotIn('pbkdf2', json.dumps(rows))
        export = self.client.get(self.url('export_csv', 'auth.user')).content.decode()
        self.assertNotIn('pbkdf2', export)

    def test_unknown_and_hidden_tables_are_404(self):
        self.assertEqual(self.client.get(self.url('rows', 'nope.nothing')).status_code, 404)
        self.assertEqual(self.client.get(self.url('rows', 'sessions.session')).status_code, 404)


class ListTests(StudioBase):
    def rows(self, key='saray_menu.menuitem', **params):
        return self.client.get(self.url('rows', key), params).json()

    def test_pagination(self):
        data = self.rows(page_size=10)
        self.assertEqual((data['total'], data['pages'], len(data['rows'])), (78, 8, 10))
        self.assertEqual((data['start'], data['end']), (1, 10))
        last = self.rows(page_size=10, page=8)
        self.assertEqual(len(last['rows']), 8)

    def test_invalid_page_size_falls_back(self):
        self.assertEqual(self.rows(page_size='abc')['page_size'], 25)
        self.assertEqual(self.rows(page_size=7)['page_size'], 25)

    def test_search_and_sort(self):
        data = self.rows(q='جوجه')
        self.assertTrue(0 < data['total'] < 78)
        by_price = self.rows(sort='-price', page_size=250)['rows']
        prices = [r['v']['price'] for r in by_price if r['v']['price'] is not None]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_search_by_primary_key(self):
        item = MenuItem.objects.first()
        data = self.rows(q=str(item.pk))
        self.assertIn(item.pk, [r['pk'] for r in data['rows']])

    def test_filters(self):
        MenuItem.objects.filter(pk=MenuItem.objects.first().pk).update(is_available=False)
        self.assertEqual(self.rows(f_is_available='0')['total'], 1)
        category = Category.objects.get(slug='pizza')
        self.assertEqual(self.rows(f_category=category.pk)['total'], category.items.count())

    def test_unknown_sort_field_is_ignored(self):
        self.assertEqual(self.rows(sort='price; DROP TABLE x')['total'], 78)

    def test_cell_formats(self):
        row = self.rows(q='سوپ خامه')['rows'][0]
        self.assertEqual(row['v']['category']['label'], str(Category.objects.get(slug='starters')))
        self.assertIsInstance(row['v']['price'], int)
        self.assertIn('/static/saray_menu/img/menu/', MenuItem.objects.get(pk=row['pk']).photo_url)


class WriteTests(StudioBase):
    def create_payload(self, **overrides):
        data = {
            'category': Category.objects.get(slug='desserts').pk,
            'name': 'کیک شکلاتی', 'name_en': 'Chocolate cake', 'slug': '', 'description': '',
            'price': '45000', 'stock_photo': '', 'is_available': 'on', 'order': '5',
        }
        data.update(overrides)
        return data

    def test_create_row_generates_slug_and_logs(self):
        response = self.client.post(self.url('rows', 'saray_menu.menuitem'), self.create_payload())
        self.assertEqual(response.status_code, 201, response.content)
        item = MenuItem.objects.get(name='کیک شکلاتی')
        self.assertEqual(item.slug, 'chocolate-cake')
        self.assertEqual(item.price, 45000)
        self.assertEqual(response.json()['row']['v']['name'], 'کیک شکلاتی')
        self.assertTrue(LogEntry.objects.filter(object_id=str(item.pk), action_flag=1).exists())

    def test_create_validation_errors(self):
        response = self.client.post(self.url('rows', 'saray_menu.menuitem'), self.create_payload(price='18', name=''))
        self.assertEqual(response.status_code, 422)
        fields = response.json()['fields']
        self.assertIn('price', fields)
        self.assertIn('name', fields)
        self.assertFalse(MenuItem.objects.filter(name_en='Chocolate cake').exists())

    def test_errors_are_english(self):
        response = self.client.post(self.url('rows', 'saray_menu.menuitem'), self.create_payload(name=''))
        self.assertIn('required', response.json()['fields']['name'][0].lower())

    def test_create_with_image_upload(self):
        from io import BytesIO

        from PIL import Image
        buffer = BytesIO()
        Image.new('RGB', (8, 8), (200, 144, 46)).save(buffer, 'PNG')
        png = buffer.getvalue()
        payload = self.create_payload(image=SimpleUploadedFile('dish.png', png, content_type='image/png'))
        with self.settings(MEDIA_ROOT=self.enterContext(__import__('tempfile').TemporaryDirectory())):
            response = self.client.post(self.url('rows', 'saray_menu.menuitem'), payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()['detail']['form']['image'].startswith('/media/menu/'))

    def test_full_update(self):
        item = MenuItem.objects.first()
        data = self.client.get(self.url('row', 'saray_menu.menuitem', item.pk)).json()['form']
        payload = {k: ('' if v is None else v) for k, v in data.items() if v is not False}
        payload['price'] = '99000'
        response = self.client.post(self.url('row', 'saray_menu.menuitem', item.pk), payload)
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertEqual(item.price, 99000)
        self.assertTrue(LogEntry.objects.filter(object_id=str(item.pk), action_flag=2).exists())

    def test_inline_patch_text_number_and_bool(self):
        item = MenuItem.objects.filter(is_available=True).first()
        url = self.url('row', 'saray_menu.menuitem', item.pk)
        response = self.post_json(url, {'field': 'name_en', 'value': 'Renamed'}, 'patch')
        self.assertEqual(response.status_code, 200, response.content)
        self.post_json(url, {'field': 'price', 'value': '123000'}, 'patch')
        self.post_json(url, {'field': 'is_available', 'value': False}, 'patch')
        item.refresh_from_db()
        self.assertEqual((item.name_en, item.price, item.is_available), ('Renamed', 123000, False))
        self.post_json(url, {'field': 'is_available', 'value': True}, 'patch')
        item.refresh_from_db()
        self.assertTrue(item.is_available)

    def test_inline_patch_validation_and_unknown_field(self):
        item = MenuItem.objects.first()
        url = self.url('row', 'saray_menu.menuitem', item.pk)
        before = item.price
        response = self.post_json(url, {'field': 'price', 'value': '18'}, 'patch')
        self.assertEqual(response.status_code, 422)
        item.refresh_from_db()
        self.assertEqual(item.price, before)
        self.assertEqual(self.post_json(url, {'field': 'id', 'value': 5}, 'patch').status_code, 400)
        self.assertEqual(self.post_json(url, {'field': 'image', 'value': 'x'}, 'patch').status_code, 400)
        self.assertEqual(self.client.patch(url, 'not json', content_type='application/json').status_code, 400)

    def test_inline_patch_foreign_key(self):
        item = MenuItem.objects.first()
        target = Category.objects.exclude(pk=item.category_id).first()
        response = self.post_json(self.url('row', 'saray_menu.menuitem', item.pk), {'field': 'category', 'value': target.pk}, 'patch')
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertEqual(item.category_id, target.pk)

    def test_unique_constraint_is_reported_not_crashed(self):
        a, b = MenuItem.objects.all()[:2]
        response = self.post_json(self.url('row', 'saray_menu.menuitem', b.pk), {'field': 'slug', 'value': a.slug}, 'patch')
        self.assertEqual(response.status_code, 422)


class ReadOnlyAndSingletonTests(StudioBase):
    def test_readonly_tables_reject_writes(self):
        user = self.admin
        url = self.url('row', 'auth.user', user.pk)
        self.assertEqual(self.client.post(url, {'username': 'hacked'}).status_code, 403)
        self.assertEqual(self.post_json(url, {'field': 'username', 'value': 'x'}, 'patch').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.post(self.url('rows', 'auth.user'), {'username': 'new'}).status_code, 403)
        self.assertEqual(self.post_json(self.url('bulk_delete', 'auth.user'), {'ids': [user.pk]}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=user.pk, username='boss').exists())

    def test_site_settings_is_a_singleton(self):
        settings_row = SiteSettings.load()
        self.assertEqual(self.client.delete(self.url('row', 'saray_menu.sitesettings', settings_row.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url('rows', 'saray_menu.sitesettings'), {'name': 'Second'}).status_code, 409)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_site_settings_can_be_edited(self):
        settings_row = SiteSettings.load()
        response = self.post_json(self.url('row', 'saray_menu.sitesettings', settings_row.pk), {'field': 'announcement', 'value': 'Closed Friday'}, 'patch')
        self.assertEqual(response.status_code, 200, response.content)
        settings_row.refresh_from_db()
        self.assertEqual(settings_row.announcement, 'Closed Friday')


class DeleteTests(StudioBase):
    def test_preview_counts_cascades(self):
        category = Category.objects.get(slug='pizza')
        preview = self.client.get(self.url('delete_preview', 'saray_menu.category', category.pk)).json()
        related = {r['table']: r['count'] for r in preview['summary']['related']}
        self.assertEqual(related['MenuItem'], category.items.count())
        self.assertEqual(related['MenuItemVariant'], MenuItemVariant.objects.filter(item__category=category).count())
        self.assertIsNone(preview['blocked'])

    def test_delete_cascades_and_logs(self):
        category = Category.objects.get(slug='pizza')
        pk = category.pk
        response = self.client.delete(self.url('row', 'saray_menu.category', pk))
        self.assertEqual(response.json(), {'deleted': 1})
        self.assertFalse(Category.objects.filter(pk=pk).exists())
        self.assertFalse(MenuItem.objects.filter(category_id=pk).exists())
        self.assertTrue(LogEntry.objects.filter(object_id=str(pk), action_flag=3).exists())

    def test_delete_missing_row_is_404(self):
        self.assertEqual(self.client.delete(self.url('row', 'saray_menu.menuitem', 999999)).status_code, 404)

    def test_bulk_delete(self):
        ids = list(MenuItem.objects.values_list('pk', flat=True)[:3])
        preview = self.post_json(self.url('bulk_delete', 'saray_menu.menuitem'), {'ids': ids, 'preview': True}).json()
        self.assertEqual(preview['summary']['selected'], 3)
        self.assertEqual(MenuItem.objects.count(), 78)
        response = self.post_json(self.url('bulk_delete', 'saray_menu.menuitem'), {'ids': ids})
        self.assertEqual(response.json(), {'deleted': 3})
        self.assertEqual(MenuItem.objects.count(), 75)

    def test_bulk_delete_validates_input(self):
        url = self.url('bulk_delete', 'saray_menu.menuitem')
        for payload in ({}, {'ids': []}, {'ids': ['1']}, {'ids': list(range(1, 600))}):
            with self.subTest(payload=str(payload)[:30]):
                self.assertEqual(self.post_json(url, payload).status_code, 400)

    def test_reservation_crud(self):
        import datetime
        data = {'name': 'Ali Test', 'phone': '09121234567', 'date': '2030-01-01', 'time': '20:00', 'guests': '4',
                'occasion': '', 'notes': '', 'status': 'pending', 'staff_note': ''}
        response = self.client.post(self.url('rows', 'reservations.reservation'), data)
        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(name='Ali Test')
        self.assertEqual(reservation.date, datetime.date(2030, 1, 1))
        self.assertEqual(len(reservation.code), 6)
        self.assertEqual(self.client.delete(self.url('row', 'reservations.reservation', reservation.pk)).status_code, 200)


class ExportTests(StudioBase):
    def test_csv_export_has_header_and_bom(self):
        response = self.client.get(self.url('export_csv', 'saray_menu.category'))
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        text = response.content.decode('utf-8')
        self.assertTrue(text.startswith('﻿id,'))
        self.assertEqual(len(text.strip().splitlines()), 10)  # header + 9 categories

    def test_csv_neutralises_formula_injection(self):
        Category.objects.filter(slug='pizza').update(name='=HYPERLINK("http://evil.example")')
        text = self.client.get(self.url('export_csv', 'saray_menu.category')).content.decode()
        self.assertIn("'=HYPERLINK", text)

    def test_csv_keeps_negative_numbers(self):
        from studio.views import csv_cell
        self.assertEqual(csv_cell(-5), '-5')
        self.assertEqual(csv_cell('-2.5'), '-2.5')
        self.assertEqual(csv_cell('@cmd'), "'@cmd")


class OptionsTests(StudioBase):
    def test_options_for_foreign_keys(self):
        options = self.client.get(self.url('options', 'saray_menu.category')).json()['options']
        self.assertEqual(len(options), 9)
        filtered = self.client.get(self.url('options', 'saray_menu.category'), {'q': 'pizza'}).json()['options']
        self.assertTrue(all('pizza' in o['label'].lower() for o in filtered))
