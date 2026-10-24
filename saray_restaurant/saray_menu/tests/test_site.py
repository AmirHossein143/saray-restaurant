import datetime
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.urls import reverse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from saray_menu.context_processors import site as site_context
from saray_menu.models import Category, SiteSettings
from saray_menu.views import load_photo_credits


class ContextProcessorTests(TestCase):
    def test_values(self):
        request = RequestFactory().get('/')
        with mock.patch('saray_menu.context_processors.timezone.localdate',
                        return_value=datetime.date(2026, 10, 22)):
            ctx = site_context(request)
        self.assertEqual(ctx['current_year_fa'], '۱۴۰۵')
        self.assertEqual(ctx['jalali_today'], 'پنج‌شنبه ۳۰ مهر ۱۴۰۵')
        self.assertEqual(ctx['site'].name, SiteSettings.load().name)
        self.assertEqual([c.slug for c in ctx['nav_categories']],
                         list(Category.objects.filter(is_active=True).values_list('slug', flat=True)))

    def test_lazy_and_hides_inactive_categories(self):
        Category.objects.filter(slug='desserts').update(is_active=False)
        request = RequestFactory().get('/')
        with self.assertNumQueries(0):
            ctx = site_context(request)
        slugs = [c.slug for c in ctx['nav_categories']]
        self.assertNotIn('desserts', slugs)
        self.assertEqual(len(slugs), 8)


class LegacyRedirectTests(TestCase):
    def test_permanent_redirects(self):
        cases = {
            '/saray-menu/': '/',
            '/saray-menu/menu/': '/menu/',
            '/index.html': '/',
            '/saray.html': '/',
            '/menu.html': '/menu/',
            '/blog.html': '/',
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                response = self.client.get(old)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response['Location'], new)

    def test_query_string_kept(self):
        response = self.client.get('/saray-menu/menu/?utm_source=x')
        self.assertEqual(response['Location'], '/menu/?utm_source=x')


class SeoTests(TestCase):
    def test_sitemap(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for path in ('/', '/menu/', '/about/', '/contact/', '/reserve/', '/credits/'):
            self.assertIn(f'<loc>http://testserver{path}</loc>', body)
        self.assertIn('<lastmod>', body)
        self.assertNotIn('/admin/', body)

    def test_robots(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)

    def test_unknown_url_is_404(self):
        response = self.client.get('/no-such-page/')
        self.assertEqual(response.status_code, 404)


class PhotoCreditsLoaderTests(TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(load_photo_credits('Z:/definitely/missing.json'), [])

    def test_list_and_dict_formats(self):
        entry = {'key': 'kabab-barg', 'title': 'Kabab', 'author': 'A', 'license': 'CC BY 4.0',
                 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
                 'source_url': 'https://commons.wikimedia.org/x', 'extra': 'ignored'}
        with tempfile.TemporaryDirectory() as tmp:
            as_list = Path(tmp) / 'a.json'
            as_list.write_text(json.dumps([entry]), encoding='utf-8')
            as_dict = Path(tmp) / 'b.json'
            as_dict.write_text(json.dumps({'credits': [entry, 'junk']}), encoding='utf-8')
            broken = Path(tmp) / 'c.json'
            broken.write_text('{not json', encoding='utf-8')
            for path in (as_list, as_dict):
                credits = load_photo_credits(path)
                self.assertEqual(len(credits), 1)
                self.assertEqual(credits[0]['author'], 'A')
                self.assertNotIn('extra', credits[0])
            with self.assertLogs('saray_menu.views', 'WARNING'):
                self.assertEqual(load_photo_credits(broken), [])


@override_settings(DEBUG=False)
class ServerErrorHandlerTests(TestCase):
    def test_server_error_handler_returns_500(self):
        from saray_menu.views import server_error

        request = RequestFactory().get('/')
        response = server_error(request)
        self.assertEqual(response.status_code, 500)

    def test_server_error_survives_broken_templates(self):
        from saray_menu import views

        request = RequestFactory().get('/')
        with mock.patch.object(views, 'render', side_effect=RuntimeError('db down')), \
                mock.patch.object(views.loader, 'get_template', side_effect=ValueError('manifest')), \
                self.assertLogs('saray_menu.views', 'ERROR'):
            response = views.server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'مشکلی پیش آمد', status_code=500)


class StaticStorageTests(SimpleTestCase):
    def test_missing_manifest_entry_does_not_raise(self):
        from saray_restaurant.storage import LenientManifestStaticFilesStorage

        storage = LenientManifestStaticFilesStorage()
        storage.hashed_files = {}
        self.assertEqual(storage.url('saray_menu/img/site/not-collected.webp'),
                         '/static/saray_menu/img/site/not-collected.webp')


class EmptyCategoryTests(TestCase):
    """A category whose dishes are all unavailable disappears from the site."""

    def setUp(self):
        from saray_menu.models import Category, MenuItem

        self.category = Category.objects.get(slug='desserts')
        MenuItem.objects.filter(category=self.category).update(is_available=False)

    def test_hidden_from_home_menu_and_navigation(self):
        for name in ('home', 'menu'):
            response = self.client.get(reverse(name))
            with self.subTest(page=name):
                self.assertNotIn(self.category, list(response.context['categories']))
                self.assertNotIn(self.category, list(response.context['nav_categories']))
        response = self.client.get(reverse('menu'))
        self.assertEqual(response.context['item_count'], 76)
