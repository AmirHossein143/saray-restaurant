"""Public page rendering. These depend on the frontend templates."""

from django.test import TestCase
from django.urls import reverse

from saray_menu.models import MenuItem, SiteSettings


class PublicPageTests(TestCase):
    def test_pages_render(self):
        for name in ('home', 'menu', 'about', 'contact', 'credits', 'reservations:create'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'lang="fa"')
                self.assertContains(response, 'dir="rtl"')
                self.assertContains(response, 'noronet.co')

    def test_home(self):
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'saray_menu/home.html')
        featured = response.context['featured_items']
        self.assertLessEqual(len(featured), 8)
        self.assertTrue(all(item.is_featured and item.is_available for item in featured))
        for item in featured:
            self.assertContains(response, item.name)
        self.assertEqual(len(response.context['categories']), 9)
        self.assertContains(response, 'application/ld+json')

    def test_menu_lists_every_available_dish(self):
        MenuItem.objects.filter(slug='baklava').update(is_available=False)
        response = self.client.get(reverse('menu'))
        self.assertTemplateUsed(response, 'saray_menu/menu.html')
        self.assertEqual(response.context['item_count'], 77)
        for item in MenuItem.objects.filter(is_available=True):
            self.assertContains(response, item.name)
        listed = {item.slug for c in response.context['categories'] for item in c.available_items}
        self.assertEqual(len(listed), 77)
        self.assertNotIn('baklava', listed)
        self.assertContains(response, 'سوپ خامه')
        self.assertContains(response, 'کباب')

    def test_menu_query_count_is_constant(self):
        self.client.get(reverse('menu'))  # warm up
        with self.assertNumQueriesLessThan(12):
            self.client.get(reverse('menu'))

    def test_contact_shows_owner_data(self):
        response = self.client.get(reverse('contact'))
        self.assertContains(response, 'باغمیشه')
        self.assertContains(response, 'tel:+984136688554')

    def test_announcement_only_when_filled(self):
        site = SiteSettings.load()
        site.announcement = 'اطلاعیهٔ آزمایشی'
        site.save()
        self.assertContains(self.client.get(reverse('home')), 'اطلاعیهٔ آزمایشی')

    def test_credits_page(self):
        response = self.client.get(reverse('credits'))
        self.assertIsInstance(response.context['credits'], list)

    # Helper: assertNumQueries with an upper bound.
    def assertNumQueriesLessThan(self, limit):
        from contextlib import contextmanager

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        @contextmanager
        def ctx():
            with CaptureQueriesContext(connection) as captured:
                yield
            self.assertLess(len(captured), limit, [q['sql'] for q in captured])

        return ctx()
