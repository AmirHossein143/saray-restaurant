from collections import Counter
from html.parser import HTMLParser
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class RestaurantPageTests(SimpleTestCase):
    pages = ('/', '/saray-menu/', '/saray-menu/menu/')

    def test_root_opens_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'saray_menu/index.html')

    def test_existing_home_url_still_works(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'saray_menu/index.html')

    def test_menu_displays_existing_dishes_and_prices(self):
        response = self.client.get(reverse('menu'))
        self.assertEqual(response.status_code, 200)
        for text in ('سوپ خامه', 'سالاد فصل', 'سالاد پاستا',
                     '۱۰۰۰۰۰', '۳۰۰۰۰۰', '۵۰۰۰۰۰'):
            self.assertContains(response, text)
        self.assertContains(response, 'class="card menu-card"', count=3)

    def test_pages_have_persian_metadata_and_one_document(self):
        for path in self.pages:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, '<html lang="fa" dir="rtl">', count=1)
                self.assertContains(response, '<body ', count=1)
                self.assertContains(response, '</body>', count=1)
                self.assertContains(response, 'name="viewport"', count=1)
                self.assertNotContains(response, 'Material Design for Bootstrap')
                html = response.content.decode()
                self.assertLess(html.index('</footer>'), html.index('</body>'))

    def test_internal_navigation_and_fragment_targets_work(self):
        for path in self.pages:
            parser = PageParser(self.client.get(path).content.decode())
            ids = [attrs['id'] for _, attrs in parser.elements if 'id' in attrs]
            self.assertEqual(len(ids), len(set(ids)), path)
            for tag, attrs in parser.elements:
                if tag != 'a':
                    continue
                target = urlsplit(attrs.get('href', ''))
                if target.scheme or target.netloc:
                    continue
                with self.subTest(path=path, href=attrs.get('href')):
                    self.assertTrue(target.path or target.fragment)
                    if target.path:
                        self.assertEqual(self.client.get(target.path).status_code, 200)
                    if target.fragment:
                        self.assertIn(target.fragment, ids)

    def test_all_page_assets_and_css_images_exist_locally(self):
        checked = set()

        def check_asset(path):
            if path in checked:
                return
            checked.add(path)
            found = finders.find(path)
            self.assertIsNotNone(found, f'Missing static asset: {path}')
            if path.endswith('.css'):
                with open(found, encoding='utf-8-sig') as stylesheet:
                    css = stylesheet.read()
                for reference in re.findall(r'url\([\'\"]?([^\s)\'\"]+)', css):
                    target = urlsplit(reference)
                    if target.scheme or not target.path:
                        continue
                    # Normalize ../ references in CSS before asking Django to find them.
                    parts = []
                    for part in (PurePosixPath(path).parent / target.path).parts:
                        if part == '..':
                            parts.pop()
                        else:
                            parts.append(part)
                    check_asset('/'.join(parts))

        for path in self.pages:
            parser = PageParser(self.client.get(path).content.decode())
            for tag, attrs in parser.elements:
                if tag not in ('img', 'script', 'link'):
                    continue
                reference = attrs.get('src') or attrs.get('href', '')
                if reference.startswith('data:'):
                    continue
                self.assertTrue(reference.startswith('/static/'), reference)
                check_asset(reference.removeprefix('/static/'))

    def test_carousel_controls_and_indicators_target_existing_slides(self):
        for path in self.pages:
            parser = PageParser(self.client.get(path).content.decode())
            carousels = {
                attrs['id'] for _, attrs in parser.elements
                if 'carousel' in attrs.get('class', '').split()
            }
            indicators = Counter()
            for _, attrs in parser.elements:
                if 'data-slide-to' in attrs:
                    target = attrs['data-target'].removeprefix('#')
                    self.assertIn(target, carousels)
                    self.assertEqual(int(attrs['data-slide-to']), indicators[target])
                    indicators[target] += 1
                if 'data-slide' in attrs:
                    self.assertIn(attrs['href'].removeprefix('#'), carousels)
            self.assertTrue(carousels)
            self.assertTrue(all(indicators[target] == 3 for target in carousels))
