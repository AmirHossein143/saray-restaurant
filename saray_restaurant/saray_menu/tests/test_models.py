import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from saray_menu.models import Category, MenuItem, MenuItemVariant, SiteSettings
from saray_menu.seed import SEED_PATH, import_menu


class SeedTests(TestCase):
    """The data migration has already loaded the seed into the test database."""

    def test_counts_after_migration(self):
        self.assertEqual(Category.objects.count(), 9)
        self.assertEqual(MenuItem.objects.count(), 78)
        self.assertEqual(MenuItemVariant.objects.count(), 12)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_import_is_idempotent(self):
        result = import_menu()
        self.assertEqual(result.categories_created, 0)
        self.assertEqual(result.items_created, 0)
        self.assertEqual(result.variants_created, 0)
        self.assertEqual(result.items_updated, 78)
        self.assertEqual(Category.objects.count(), 9)
        self.assertEqual(MenuItem.objects.count(), 78)
        self.assertEqual(MenuItemVariant.objects.count(), 12)

    def test_import_restores_seed_values(self):
        item = MenuItem.objects.get(slug='cream-barley-soup')
        item.price = 1
        item.save()
        call_command('import_menu', stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(item.price, 15000)

    def test_seed_content(self):
        data = json.loads(SEED_PATH.read_text(encoding='utf-8'))
        first = data['categories'][0]
        category = Category.objects.get(slug=first['slug'])
        self.assertEqual(category.name, first['name'])
        self.assertEqual(category.stock_photo, first['photo'])
        self.assertEqual(category.icon, first['icon'])
        self.assertEqual(list(Category.objects.values_list('slug', flat=True)),
                         [c['slug'] for c in data['categories']])
        pizza = MenuItem.objects.filter(category__slug='pizza').first()
        self.assertIsNone(pizza.price)
        self.assertEqual(pizza.variants.count(), 2)
        self.assertEqual(pizza.min_price, min(v.price for v in pizza.variants.all()))

    def test_import_command_with_file_and_errors(self):
        data = {'categories': [{
            'slug': 'specials', 'name': 'ویژه', 'icon': 'flame', 'photo': '',
            'items': [{'slug': 'new-dish', 'name': 'غذای تازه', 'price': 120000,
                       'variants': [{'label': 'بزرگ', 'price': 150000}]}],
        }]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'menu.json'
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            out = StringIO()
            call_command('import_menu', '--file', str(path), stdout=out)
            self.assertIn('items +1', out.getvalue())
            bad = Path(tmp) / 'bad.json'
            bad.write_text('{"nope": 1}', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('import_menu', '--file', str(bad), stdout=StringIO())
        self.assertEqual(MenuItem.objects.get(slug='new-dish').variants.get().price, 150000)
        with self.assertRaises(CommandError):
            call_command('import_menu', '--file', 'does-not-exist.json', stdout=StringIO())


class SiteSettingsTests(TestCase):
    def test_defaults(self):
        site = SiteSettings.load()
        self.assertEqual(site.pk, 1)
        self.assertEqual(site.name, 'رستوران سارای')
        self.assertEqual(site.address, 'تبریز، باغمیشه، روبروی بازار ماهی')
        self.assertEqual(site.phone, '+984136688554')
        self.assertEqual(site.phone_display, '۰۴۱-۳۶۶۸۸۵۵۴')
        self.assertEqual(site.opening_hours_text, 'همه‌روزه از ۱۰ صبح تا ۱۲ شب')
        self.assertTrue(site.reservations_enabled)
        self.assertEqual(site.instagram_url, '')
        self.assertIsNone(site.latitude)
        self.assertFalse(site.has_location)
        self.assertEqual(site.tel_href, 'tel:+984136688554')
        self.assertGreaterEqual(len(site.about_paragraphs), 2)

    def test_singleton(self):
        SiteSettings(name='دیگر').save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().name, 'دیگر')
        SiteSettings.load().delete()
        self.assertEqual(SiteSettings.objects.count(), 1)


class PhotoUrlTests(TestCase):
    def setUp(self):
        self.item = MenuItem.objects.get(slug='cream-barley-soup')

    def test_uploaded_image_wins(self):
        self.item.image = 'menu/my-soup.jpg'
        self.assertEqual(self.item.photo_url, '/media/menu/my-soup.jpg')
        self.assertEqual(self.item.photo_sm_url, '/media/menu/my-soup.jpg')

    def test_stock_photo_when_file_exists(self):
        with mock.patch('saray_menu.models.static_file_exists', return_value=True):
            self.assertEqual(self.item.photo_url, '/static/saray_menu/img/menu/barley-soup.webp')
            self.assertEqual(self.item.photo_sm_url, '/static/saray_menu/img/menu/barley-soup-sm.webp')

    def test_small_falls_back_to_full_size(self):
        exists = lambda path: not path.endswith('-sm.webp')  # noqa: E731
        with mock.patch('saray_menu.models.static_file_exists', side_effect=exists):
            self.assertEqual(self.item.photo_sm_url, '/static/saray_menu/img/menu/barley-soup.webp')

    def test_placeholder_when_stock_photo_missing(self):
        with mock.patch('saray_menu.models.static_file_exists', return_value=False):
            self.assertEqual(self.item.photo_url, '/static/saray_menu/img/ui/placeholder.webp')
        self.item.stock_photo = ''
        self.assertEqual(self.item.photo_url, '/static/saray_menu/img/ui/placeholder.webp')

    def test_category_photo(self):
        category = Category.objects.get(slug='starters')
        with mock.patch('saray_menu.models.static_file_exists', return_value=True):
            self.assertEqual(category.photo_url, '/static/saray_menu/img/menu/shirazi-salad.webp')
            self.assertEqual(category.photo_sm_url, '/static/saray_menu/img/menu/shirazi-salad-sm.webp')
        category.image = 'categories/c.webp'
        self.assertEqual(category.photo_url, '/media/categories/c.webp')
        self.assertEqual(category.get_absolute_url(), '/menu/#starters')

    def test_min_price(self):
        self.assertEqual(self.item.min_price, 15000)
        drink = MenuItem.objects.filter(price__isnull=True, variants__isnull=True).first()
        self.assertIsNotNone(drink)
        self.assertIsNone(drink.min_price)


class EnsureAdminCommandTests(TestCase):
    def test_does_nothing_without_env(self):
        from django.contrib.auth import get_user_model

        with mock.patch.dict('os.environ', {'DJANGO_ADMIN_USER': '', 'DJANGO_ADMIN_PASSWORD': ''}):
            call_command('ensure_admin', stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())

    def test_creates_superuser_from_env(self):
        from django.contrib.auth import get_user_model

        env = {'DJANGO_ADMIN_USER': 'owner', 'DJANGO_ADMIN_PASSWORD': 'kabab-Koobideh-2026!'}
        with mock.patch.dict('os.environ', env):
            call_command('ensure_admin', stdout=StringIO())
            call_command('ensure_admin', stdout=StringIO())  # second run is a no-op
        user = get_user_model().objects.get(username='owner')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password('kabab-Koobideh-2026!'))

    def test_rejects_weak_password(self):
        with mock.patch.dict('os.environ', {'DJANGO_ADMIN_USER': 'owner', 'DJANGO_ADMIN_PASSWORD': '123'}):
            with self.assertRaises(CommandError):
                call_command('ensure_admin', stdout=StringIO())
