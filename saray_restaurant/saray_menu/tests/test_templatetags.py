import datetime
import json
import re

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase

from saray_menu.models import SiteSettings
from saray_menu.templatetags.saray import fa_digits, jalali, jalali_long, price_short, thousands, toman
from saray_menu.utils import ascii_digits, group_thousands


class FilterTests(SimpleTestCase):
    def test_fa_digits(self):
        self.assertEqual(fa_digits('041-36688554'), '۰۴۱-۳۶۶۸۸۵۵۴')
        self.assertEqual(fa_digits(2026), '۲۰۲۶')
        self.assertEqual(fa_digits(None), '')
        self.assertEqual(fa_digits('بدون عدد'), 'بدون عدد')

    def test_toman(self):
        self.assertEqual(toman(250000), '۲۵۰ هزار تومان')
        self.assertEqual(toman(1500000), '۱٬۵۰۰ هزار تومان')
        self.assertEqual(toman(250500), '۲۵۰٬۵۰۰ تومان')
        self.assertEqual(toman(0), '۰ تومان')
        self.assertEqual(toman(None), '')
        self.assertEqual(toman(''), '')
        self.assertEqual(toman('abc'), '')

    def test_price_short(self):
        self.assertEqual(price_short(250000), '۲۵۰')
        self.assertEqual(price_short(1250000), '۱٬۲۵۰')
        self.assertEqual(price_short(250500), '۲۵۰٫۵')
        self.assertEqual(price_short(None), '')

    def test_thousands(self):
        self.assertEqual(thousands(1250000), '۱٬۲۵۰٬۰۰۰')
        self.assertEqual(group_thousands(999), '۹۹۹')

    def test_jalali_filters(self):
        self.assertEqual(jalali(datetime.date(2026, 10, 23)), '۱ آبان ۱۴۰۵')
        self.assertEqual(jalali_long(datetime.date(2026, 10, 23)), 'جمعه ۱ آبان ۱۴۰۵')
        self.assertEqual(jalali('2026-03-21'), '۱ فروردین ۱۴۰۵')
        self.assertEqual(jalali(None), '')
        self.assertEqual(jalali('not a date'), '')

    def test_ascii_digits(self):
        self.assertEqual(ascii_digits('۰۹۱۲-٣٤٥'), '0912-345')

    def test_filters_in_templates(self):
        out = Template('{% load saray %}{{ p|toman }}|{{ p|price_short }}|{{ d|jalali }}').render(
            Context({'p': 30000, 'd': datetime.date(2026, 3, 21)})
        )
        self.assertEqual(out, '۳۰ هزار تومان|۳۰|۱ فروردین ۱۴۰۵')


class JsonLdTests(TestCase):
    def render(self, **context):
        request = RequestFactory().get('/')
        return Template('{% load saray %}{% json_ld_restaurant %}').render(
            Context({'request': request, **context})
        )

    def parse(self, html):
        match = re.fullmatch(r'<script type="application/ld\+json">(.*)</script>', html, re.S)
        self.assertIsNotNone(match, html)
        return json.loads(match.group(1))

    def test_only_real_data(self):
        data = self.parse(self.render(site=SiteSettings.load()))
        self.assertEqual(data['@type'], 'Restaurant')
        self.assertEqual(data['name'], 'رستوران سارای')
        self.assertEqual(data['telephone'], '+984136688554')
        self.assertEqual(data['address']['streetAddress'], 'تبریز، باغمیشه، روبروی بازار ماهی')
        self.assertEqual(data['url'], 'http://testserver/')
        self.assertEqual(data['hasMenu'], 'http://testserver/menu/')
        self.assertEqual(data['openingHours'], 'Mo-Su 10:00-23:59')
        self.assertIn('servesCuisine', data)
        # Nothing the owner has not supplied.
        for key in ('geo', 'sameAs', 'aggregateRating', 'review', 'foundingDate', 'award'):
            self.assertNotIn(key, data)

    def test_optional_data_when_filled(self):
        site = SiteSettings.load()
        site.latitude, site.longitude = 38.08, 46.29
        site.instagram_url = 'https://instagram.com/example'
        site.save()
        data = self.parse(self.render(site=SiteSettings.load()))
        self.assertEqual(data['geo']['latitude'], 38.08)
        self.assertEqual(data['sameAs'], ['https://instagram.com/example'])

    def test_script_cannot_be_broken_out_of(self):
        site = SiteSettings.load()
        site.name = '</script><script>alert(1)</script>'
        html = self.render(site=site)
        self.assertEqual(html.count('</script>'), 1)

    def test_loads_settings_without_context(self):
        data = self.parse(self.render())
        self.assertEqual(data['name'], 'رستوران سارای')
