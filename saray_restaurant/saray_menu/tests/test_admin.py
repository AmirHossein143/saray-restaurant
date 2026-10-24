import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservations.models import Reservation
from saray_menu.models import Category, MenuItem, SiteSettings


class AdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('boss', 'boss@example.com', 'x-Strong-Pass-1')
        today = timezone.localdate()
        cls.today_res = Reservation.objects.create(
            name='مهمان امروز', phone='09121234567', date=today,
            time=datetime.time(20, 0), guests=4, occasion='birthday',
        )
        cls.later_res = Reservation.objects.create(
            name='مهمان فردا', phone='04136688554', date=today + datetime.timedelta(days=1),
            time=datetime.time(13, 30), guests=2, status=Reservation.Status.CONFIRMED,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پنل مدیریت رستوران سارای')
        self.assertContains(response, 'رزروهای امروز')
        self.assertContains(response, 'در انتظار تایید')
        self.assertContains(response, 'غذاهای موجود')
        self.assertContains(response, 'مشاهده سایت')
        self.assertContains(response, 'مهمان امروز')
        # Tomorrow's guest is only in the "فردا" list, after today's list.
        html = response.content.decode()
        self.assertLess(html.index('مهمان امروز'), html.index('sr-today-list--tomorrow'))
        self.assertGreater(html.index('مهمان فردا'), html.index('sr-today-list--tomorrow'))
        self.assertContains(response, '۷۸')  # 78 items
        self.assertContains(response, 'saray_menu/css/admin.css')
        self.assertContains(response, 'saray_menu/fonts/fonts.css')
        self.assertContains(response, 'dir="rtl"')

    def test_login_page_branded(self):
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پنل مدیریت رستوران سارای')

    def test_changelists(self):
        for model in ('saray_menu_category', 'saray_menu_menuitem', 'reservations_reservation'):
            with self.subTest(model=model):
                response = self.client.get(reverse(f'admin:{model}_changelist'), follow=True)
                self.assertEqual(response.status_code, 200)

    def test_menuitem_changelist_content(self):
        response = self.client.get(reverse('admin:saray_menu_menuitem_changelist'))
        self.assertContains(response, 'سوپ خامه')
        self.assertContains(response, '۱۵ هزار تومان')
        self.assertContains(response, 'class="sr-thumb"')
        pizza = self.client.get(reverse('admin:saray_menu_menuitem_changelist'), {'q': 'پیتزا'})
        self.assertContains(pizza, 'هزار تومان')

    def test_reservation_changelist_filters_and_badges(self):
        url = reverse('admin:reservations_reservation_changelist')
        for when in ('today', 'tomorrow', 'week', 'upcoming', 'past'):
            with self.subTest(when=when):
                self.assertEqual(self.client.get(url, {'when': when}).status_code, 200)
        response = self.client.get(url, {'when': 'today'})
        self.assertContains(response, self.today_res.code)
        self.assertNotContains(response, self.later_res.code)
        self.assertContains(response, 'sr-badge--pending')
        self.assertContains(response, 'href="tel:09121234567"')
        search = self.client.get(url, {'q': self.later_res.code})
        self.assertContains(search, 'مهمان فردا')

    def test_change_and_add_forms(self):
        item = MenuItem.objects.get(slug='chef-pizza')
        urls = [
            reverse('admin:saray_menu_menuitem_change', args=[item.pk]),
            reverse('admin:saray_menu_menuitem_add'),
            reverse('admin:saray_menu_category_change', args=[item.category_id]),
            reverse('admin:saray_menu_category_add'),
            reverse('admin:reservations_reservation_change', args=[self.today_res.pk]),
            reverse('admin:reservations_reservation_add'),
            reverse('admin:saray_menu_sitesettings_change', args=[1]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_site_settings_singleton(self):
        response = self.client.get(reverse('admin:saray_menu_sitesettings_changelist'))
        self.assertRedirects(response, reverse('admin:saray_menu_sitesettings_change', args=[1]))
        self.assertEqual(self.client.get(reverse('admin:saray_menu_sitesettings_add')).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('admin:saray_menu_sitesettings_delete', args=[1])).status_code, 403,
        )

    def test_site_settings_save(self):
        url = reverse('admin:saray_menu_sitesettings_change', args=[1])
        site = SiteSettings.load()
        data = {
            'name': site.name, 'tagline': site.tagline, 'about_text': site.about_text,
            'announcement': 'نوروز تعطیل نیستیم', 'phone': site.phone, 'phone_display': site.phone_display,
            'address': site.address, 'map_url': '', 'latitude': '', 'longitude': '',
            'opening_hours_text': site.opening_hours_text, 'opens_at': '10:00', 'closes_at': '23:59',
            'instagram_url': '', 'telegram_url': '', 'reservations_enabled': 'on',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and
                         response.context['adminform'].form.errors)
        self.assertEqual(SiteSettings.load().announcement, 'نوروز تعطیل نیستیم')

    def test_menuitem_actions(self):
        url = reverse('admin:saray_menu_menuitem_changelist')
        ids = list(MenuItem.objects.filter(category__slug='desserts').values_list('pk', flat=True))
        self.client.post(url, {'action': 'make_unavailable', '_selected_action': ids})
        self.assertFalse(MenuItem.objects.filter(pk__in=ids, is_available=True).exists())
        self.client.post(url, {'action': 'make_available', '_selected_action': ids})
        self.assertFalse(MenuItem.objects.filter(pk__in=ids, is_available=False).exists())

    def test_reservation_actions(self):
        url = reverse('admin:reservations_reservation_changelist')
        for action, status in (('mark_confirmed', 'confirmed'), ('mark_seated', 'seated'),
                               ('mark_no_show', 'no_show'), ('mark_cancelled', 'cancelled')):
            with self.subTest(action=action):
                self.client.post(url, {'action': action, '_selected_action': [self.today_res.pk]})
                self.today_res.refresh_from_db()
                self.assertEqual(self.today_res.status, status)

    def test_category_changelist_counts(self):
        response = self.client.get(reverse('admin:saray_menu_category_changelist'))
        self.assertContains(response, Category.objects.get(slug='chelow-kabab').name)
        self.assertContains(response, '۱۸')  # 18 kababs


# --------------------------------------------------------------------------
# Admin hardening for the owner (prices, slugs, translations, dashboard)
# --------------------------------------------------------------------------

from django import forms as dj_forms  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils.safestring import mark_safe  # noqa: E402

from saray_menu.admin import PriceField, persian_digits_html, unique_slug  # noqa: E402
from saray_menu.models import MenuItemVariant  # noqa: E402
from saray_menu.templatetags.saray_admin import saray_dashboard  # noqa: E402
from saray_menu.utils import ascii_digits  # noqa: E402


def changelist_data(items, **overrides):
    """POST data for the MenuItem changelist's list_editable formset."""
    data = {
        'form-TOTAL_FORMS': str(len(items)), 'form-INITIAL_FORMS': str(len(items)),
        'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000', '_save': 'ذخیره',
    }
    for i, item in enumerate(items):
        data[f'form-{i}-id'] = str(item.pk)
        data[f'form-{i}-price'] = '' if item.price is None else str(item.price)
        if item.is_available:
            data[f'form-{i}-is_available'] = 'on'
        if item.is_featured:
            data[f'form-{i}-is_featured'] = 'on'
    data.update(overrides)
    return data


class PriceFieldTests(TestCase):
    def test_accepts_separators_and_persian_digits(self):
        field = PriceField()
        for raw, expected in (
            ('18,000', 18000), ('۲۵۰٬۰۰۰', 250000), ('250000', 250000), ('۲۵۰،۰۰۰', 250000),
            (' 1 200 000 ', 1200000), ('٣٥٠٠٠', 35000), ('250,000 تومان', 250000),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(field.clean(raw), expected)

    def test_rejects_toman_typos_and_garbage(self):
        field = PriceField()
        with self.assertRaises(dj_forms.ValidationError) as ctx:
            field.clean('18')
        self.assertIn('۱۸٬۰۰۰', ctx.exception.messages[0])  # "did you mean 18,000?"
        for raw in ('abc', '18.5', '-5000', '0', '999', '100000001'):
            with self.subTest(raw=raw), self.assertRaises(dj_forms.ValidationError):
                field.clean(raw)

    def test_optional_price_can_be_left_empty(self):
        self.assertIsNone(PriceField(required=False).clean(''))
        with self.assertRaises(dj_forms.ValidationError):
            PriceField().clean('')

    def test_widget(self):
        html = PriceField().widget.render('price', 250000)
        self.assertIn('inputmode="numeric"', html)
        self.assertIn('dir="ltr"', html)
        self.assertIn('value="250,000"', html)
        self.assertNotIn('type="number"', html)


class AdminOwnerFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('owner', 'o@example.com', 'x-Strong-Pass-1')

    def setUp(self):
        self.client.force_login(self.user)

    # ----- prices -----------------------------------------------------------

    def test_list_editable_price_with_thousands_separator(self):
        url = reverse('admin:saray_menu_menuitem_changelist')
        items = list(MenuItem.objects.all()[:50])
        response = self.client.post(url, changelist_data(items, **{'form-0-price': '18,000'}), follow=True)
        items[0].refresh_from_db()
        self.assertEqual(items[0].price, 18000)
        message = [str(m) for m in response.context['messages']][0]
        self.assertIn('۱ مورد با موفقیت ذخیره شد', message)  # Persian digit, no "غذاها"

    def test_list_editable_rejects_tiny_price(self):
        url = reverse('admin:saray_menu_menuitem_changelist')
        items = list(MenuItem.objects.all()[:50])
        before = items[0].price
        response = self.client.post(url, changelist_data(items, **{'form-0-price': '18'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'منظورتان ۱۸٬۰۰۰ تومان بود؟')
        self.assertContains(response, 'لطفاً خطای زیر را برطرف کنید.')
        items[0].refresh_from_db()
        self.assertEqual(items[0].price, before)

    def _item_post(self, **overrides):
        category = Category.objects.first()
        data = {
            'category': category.pk, 'name': 'کباب تست', 'name_en': '', 'slug': '',
            'description': '', 'price': '۲۵۰٬۰۰۰', 'is_available': 'on', 'order': '0', 'stock_photo': '',
            'variants-TOTAL_FORMS': '0', 'variants-INITIAL_FORMS': '0',
            'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000',
        }
        data.update(overrides)
        return data

    def test_add_item_without_english_name_or_slug(self):
        url = reverse('admin:saray_menu_menuitem_add')
        response = self.client.post(url, self._item_post())
        self.assertEqual(response.status_code, 302)
        item = MenuItem.objects.get(name='کباب تست')
        self.assertEqual(item.price, 250000)
        self.assertEqual(item.slug, 'کباب-تست')
        # Same name again → unique slug; an empty price means "no listed price".
        self.client.post(url, self._item_post(price=''))
        second = MenuItem.objects.filter(name='کباب تست').exclude(pk=item.pk).get()
        self.assertEqual(second.slug, 'کباب-تست-2')
        self.assertIsNone(second.price)
        # The Persian slug survives a later edit.
        change = reverse('admin:saray_menu_menuitem_change', args=[item.pk])
        response = self.client.post(change, self._item_post(slug=item.slug, price='300000'))
        self.assertEqual(response.status_code, 302)

    def test_add_item_slug_from_english_name_and_duplicate_slug_error(self):
        url = reverse('admin:saray_menu_menuitem_add')
        self.client.post(url, self._item_post(name_en='Test Kabab'))
        self.assertTrue(MenuItem.objects.filter(slug='test-kabab').exists())
        response = self.client.post(url, self._item_post(slug='chef-pizza'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این نامک قبلاً')
        # Django shows a collapsible section expanded when it holds an error.
        self.assertNotRegex(response.content.decode(), r'<summary>\s*<h2[^>]*>تنظیمات پیشرفته')

    def test_variant_inline_price_is_validated(self):
        url = reverse('admin:saray_menu_menuitem_add')
        data = self._item_post(price='', **{
            'variants-TOTAL_FORMS': '2',
            'variants-0-label': 'کوچک', 'variants-0-price': '120,000', 'variants-0-order': '0',
            'variants-1-label': 'بزرگ', 'variants-1-price': '160', 'variants-1-order': '1',
        })
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'منظورتان ۱۶۰٬۰۰۰ تومان بود؟')
        data['variants-1-price'] = '۱۶۰٬۰۰۰'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(
            sorted(MenuItemVariant.objects.filter(item__name='کباب تست').values_list('price', flat=True)),
            [120000, 160000],
        )

    def test_add_category_without_slug(self):
        response = self.client.post(reverse('admin:saray_menu_category_add'), {
            'name': 'صبحانه', 'description': '', 'icon': 'cup', 'is_active': 'on',
            'name_en': '', 'slug': '', 'stock_photo': '', 'order': '20',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-name': 'املت', 'items-0-price': '۹۵٬۰۰۰', 'items-0-is_available': 'on', 'items-0-order': '0',
        })
        self.assertEqual(response.status_code, 302)
        category = Category.objects.get(name='صبحانه')
        self.assertEqual(category.slug, 'صبحانه')
        item = category.items.get()
        self.assertEqual((item.slug, item.price), ('املت', 95000))

    def test_unique_slug_fallback(self):
        self.assertTrue(unique_slug(MenuItem, '').startswith('item-'))
        self.assertEqual(unique_slug(MenuItem, 'chef-pizza'), 'chef-pizza-2')

    def test_stock_photo_select_and_photo_filter(self):
        item = MenuItem.objects.get(slug='chef-pizza')
        response = self.client.get(reverse('admin:saray_menu_menuitem_change', args=[item.pk]))
        self.assertContains(response, '<select name="stock_photo"')
        self.assertContains(response, 'تنظیمات پیشرفته')
        url = reverse('admin:saray_menu_menuitem_changelist')
        self.assertEqual(self.client.get(url, {'photo': 'uploaded'}).context['cl'].result_count, 0)
        self.assertEqual(
            self.client.get(url, {'photo': 'stock'}).context['cl'].result_count,
            MenuItem.objects.filter(image='').exclude(stock_photo='').count(),
        )

    # ----- translations -------------------------------------------------------

    def test_no_english_leftovers(self):
        response = self.client.get(reverse('admin:saray_menu_menuitem_changelist'))
        html = response.content.decode()
        for english in ('>Run<', 'Select an option', 'Filter by', 'Search ', 'Pagination', 'alt="Search"'):
            with self.subTest(english=english):
                self.assertNotIn(english, html)
        self.assertIn('>اجرا<', html)
        self.assertIn('— انتخاب کنید —', html)
        self.assertIn('حذف موارد انتخاب‌شده', html)
        self.assertIn('۷۸ غذا', html)  # paginator: Persian digits, singular noun

    def test_persian_digits_html_keeps_links(self):
        message = mark_safe('غذا «<a href="/admin/saray_menu/menuitem/12/change/">پیتزا 28</a>» ذخیره شد.')
        converted = persian_digits_html(message)
        self.assertIn('/menuitem/12/change/', converted)
        self.assertIn('پیتزا ۲۸', converted)

    # ----- site settings ------------------------------------------------------

    def test_site_settings_widgets(self):
        response = self.client.get(reverse('admin:saray_menu_sitesettings_change', args=[1]))
        html = response.content.decode()
        self.assertRegex(html, r'<input[^>]*name="phone"[^>]*dir="ltr"|<input[^>]*dir="ltr"[^>]*name="phone"')
        self.assertIn('<select name="opens_at"', html)
        self.assertIn('برچسب «باز است / بسته است»', html)


class DashboardConsistencyTests(TestCase):
    """Every dashboard number equals the row count of the list it links to."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('boss', 'boss@example.com', 'x-Strong-Pass-1')
        today = timezone.localdate()
        day = datetime.timedelta(days=1)
        rows = [
            (today, 'pending'), (today, 'confirmed'), (today, 'cancelled'), (today, 'no_show'),
            (today, 'seated'), (today + day, 'pending'), (today + 6 * day, 'confirmed'),
            (today + 7 * day, 'pending'), (today - day, 'pending'), (today + 3 * day, 'cancelled'),
        ]
        for i, (date, status) in enumerate(rows):
            Reservation.objects.create(
                name=f'مهمان {i}', phone='09121234567', date=date, time=datetime.time(20, 0),
                guests=2, status=status,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_card_counts_match_linked_lists(self):
        request = RequestFactory().get('/admin/')
        request.user = self.user
        dash = saray_dashboard({'request': request})['reservations']
        expected = {'today': 3, 'pending': 3, 'week': 5}
        for card, count in expected.items():
            with self.subTest(card=card):
                self.assertEqual(int(ascii_digits(dash[f'{card}_count'])), count)
                response = self.client.get(dash[f'{card}_url'])
                self.assertEqual(response.context['cl'].result_count, count)
        self.assertEqual(len(dash['tomorrow']), 1)

    def test_quick_status_buttons(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'sr-qbtn--confirm')
        pending = Reservation.objects.get(name='مهمان 0')
        url = reverse('admin:reservations_reservation_quick_status', args=[pending.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {'status': 'confirmed', 'next': '/admin/'})
        self.assertRedirects(response, '/admin/')
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'confirmed')
        # A status that is not a quick action, and an off-site redirect, are refused.
        response = self.client.post(url, {'status': 'no_show', 'next': 'https://evil.example/'})
        self.assertRedirects(response, reverse('admin:index'))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'confirmed')

    def test_quick_status_needs_change_permission(self):
        viewer = get_user_model().objects.create_user('viewer', password='x-Strong-Pass-1', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_reservation'))
        self.client.force_login(viewer)
        reservation = Reservation.objects.get(name='مهمان 0')
        response = self.client.get(reverse('admin:index'))
        self.assertNotContains(response, 'sr-qbtn')
        url = reverse('admin:reservations_reservation_quick_status', args=[reservation.pk])
        self.assertEqual(self.client.post(url, {'status': 'cancelled'}).status_code, 403)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, 'pending')
