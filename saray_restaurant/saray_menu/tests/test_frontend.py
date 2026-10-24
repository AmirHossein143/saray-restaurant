"""Frontend template contracts: accessibility wiring, SEO tags and graceful
fallbacks (reservations disabled, empty categories, no phone number)."""

import datetime
import re
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from saray_menu.models import MenuItem, SiteSettings

TEHRAN = ZoneInfo('Asia/Tehran')


class SeoTagTests(TestCase):
    def test_og_image_is_the_social_card(self):
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn('saray_menu/img/brand/og-image.jpg', html)
        self.assertIn('<meta property="og:image:width" content="1200">', html)
        self.assertIn('<meta property="og:image:height" content="630">', html)

    def test_each_page_has_its_own_og_description(self):
        seen = set()
        for name in ('home', 'menu', 'about', 'contact', 'credits', 'reservations:create'):
            html = self.client.get(reverse(name)).content.decode()
            match = re.search(r'<meta property="og:description" content="([^"]+)">', html)
            self.assertIsNotNone(match, name)
            seen.add(match.group(1))
        self.assertEqual(len(seen), 6)

    def test_404_has_no_canonical_or_og_url(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)
        html = response.content.decode()
        self.assertNotIn('rel="canonical"', html)
        self.assertNotIn('og:url', html)
        self.assertIn('noindex', html)


class HomeTemplateTests(TestCase):
    def test_extra_hero_slides_are_deferred(self):
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn("hero-1-md.webp 1000w", html)
        self.assertEqual(html.count('class="hero__slide"'), 2)
        self.assertEqual(len(re.findall(r'class="hero__slide"[^>]*data-src="[^"]+hero-[23]\.webp"', html)), 2)
        self.assertNotIn('aria-pressed="false" data-slide-pause', html)
        self.assertNotIn('data-slide-pause aria-pressed', html)

    def test_scroll_cue_targets_an_existing_section(self):
        MenuItem.objects.update(is_featured=False)
        html = self.client.get(reverse('home')).content.decode()
        target = re.search(r'class="hero__scroll" href="#([\w-]+)"', html).group(1)
        self.assertIn(f'id="{target}"', html)

    def test_empty_category_has_no_tile(self):
        MenuItem.objects.filter(category__slug='desserts').update(is_available=False)
        html = self.client.get(reverse('home')).content.decode()
        self.assertNotIn(reverse('menu') + '#desserts"', html.split('class="cat-grid"')[1].split('</ul>')[0])
        self.assertIn(reverse('menu') + '#grills"', html)

    def test_reservations_disabled_offers_a_call_instead(self):
        site = SiteSettings.load()
        site.reservations_enabled = False
        site.save()
        html = self.client.get(reverse('home')).content.decode()
        self.assertNotIn('رزرو آنلاین', html)
        self.assertIn('رزرو تلفنی', html)
        self.assertIn(f'href="tel:{site.phone}"', html)


class MenuTemplateTests(TestCase):
    def test_empty_category_is_left_out(self):
        MenuItem.objects.filter(category__slug='desserts').update(is_available=False)
        html = self.client.get(reverse('menu')).content.decode()
        self.assertNotIn('data-tab="desserts"', html)
        self.assertNotIn('id="desserts"', html)
        self.assertIn('data-tab="grills"', html)

    def test_no_items_shows_empty_state_without_phone_link(self):
        MenuItem.objects.update(is_available=False)
        site = SiteSettings.load()
        site.phone = ''
        site.save()
        html = self.client.get(reverse('menu')).content.decode()
        self.assertIn('منو به‌زودی به‌روز می‌شود', html)
        self.assertNotIn('href="tel:', html)
        self.assertNotIn('data-cat-tabs', html)


class ReservationTemplateTests(TestCase):
    def test_server_errors_match_django_aria_describedby(self):
        response = self.client.post(reverse('reservations:create'), {
            'name': '', 'phone': '123', 'guests': '2', 'date': '', 'time': '',
        })
        html = response.content.decode()
        for field in ('name', 'phone', 'date', 'time'):
            with self.subTest(field=field):
                self.assertIn(f'id="id_{field}_error"', html)
        # Django points the inputs at those containers
        self.assertRegex(html, r'<input[^>]*aria-describedby="[^"]*id_name_error[^"]*"[^>]*id="id_name"')
        # radio groups are described by their error list via the fieldset
        self.assertIn('aria-describedby="id_date_error"', html)
        self.assertIn('aria-describedby="id_time_error"', html)
        self.assertIn('id="id_phone_hint"', html)
        self.assertIn('data-client-alert', html)

    def test_today_chip_marked_full_late_at_night(self):
        late = datetime.datetime(2026, 10, 22, 22, 30, tzinfo=TEHRAN)
        with mock.patch('django.utils.timezone.localtime', return_value=late):
            html = self.client.get(reverse('reservations:create')).content.decode()
        chip = re.search(r'<label class="date-chip is-today is-full">.*?</label>', html, re.S)
        self.assertIsNotNone(chip)
        self.assertIn('disabled', chip.group(0))
        self.assertIn('تکمیل', chip.group(0))
        self.assertNotIn('checked', chip.group(0))

    def test_today_chip_open_in_the_afternoon(self):
        afternoon = datetime.datetime(2026, 10, 22, 15, 0, tzinfo=TEHRAN)
        with mock.patch('django.utils.timezone.localtime', return_value=afternoon):
            html = self.client.get(reverse('reservations:create')).content.decode()
        self.assertNotIn('is-full', html)

    def test_disabled_aside_does_not_promise_online_booking(self):
        site = SiteSettings.load()
        site.reservations_enabled = False
        site.save()
        html = self.client.get(reverse('reservations:create')).content.decode()
        self.assertNotIn('کد رزرو بگیرید', html)
        self.assertNotIn('رزرو آنلاین برای امروز', html)
        self.assertIn('رزرو تلفنی', html)
        self.assertNotIn('data-reserve-form', html)


class HeaderTests(TestCase):
    def test_phone_link_text_is_visually_hidden_not_removed(self):
        html = self.client.get(reverse('about')).content.decode()
        link = re.search(r'<a class="header-phone"[^>]*>.*?</a>', html, re.S).group(0)
        self.assertIn('header-phone__text', link)
        self.assertIn('تماس و رزرو', link)
