import datetime
import zoneinfo
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from saray_menu.models import SiteSettings

from .forms import (
    MESSAGES,
    ReservationForm,
    date_choices,
    normalize_phone,
    time_choices,
    time_slots,
)
from .models import CODE_ALPHABET, Reservation

TEHRAN = zoneinfo.ZoneInfo('Asia/Tehran')
# Thursday 30 Mehr 1405, 15:10 in Tehran.
NOW = datetime.datetime(2026, 10, 22, 15, 10, tzinfo=TEHRAN)
TODAY = NOW.date()
TOMORROW = TODAY + datetime.timedelta(days=1)


def form_data(**overrides):
    data = {
        'name': 'سارا محمدی',
        'phone': '09121234567',
        'date': TOMORROW.isoformat(),
        'time': '20:00',
        'guests': '4',
        'occasion': '',
        'notes': '',
        'website': '',
    }
    data.update(overrides)
    return data


class ChoicesTests(TestCase):
    def test_time_slots(self):
        slots = time_slots()
        self.assertEqual(slots[0], datetime.time(12, 0))
        self.assertEqual(slots[-1], datetime.time(22, 30))
        self.assertEqual(len(slots), 22)

    def test_time_choices(self):
        choices = time_choices(NOW)
        self.assertEqual(choices[0], {'value': '12:00', 'label': '۱۲:۰۰', 'available_today': False})
        by_value = {c['value']: c for c in choices}
        self.assertFalse(by_value['16:00']['available_today'])  # 50 minutes away
        self.assertTrue(by_value['16:30']['available_today'])
        self.assertEqual(by_value['22:30']['label'], '۲۲:۳۰')

    def test_date_choices(self):
        choices = date_choices(NOW)
        self.assertEqual(len(choices), 31)
        self.assertEqual(choices[0]['value'], '2026-10-22')
        self.assertEqual(choices[0]['label'], 'پنج‌شنبه ۳۰ مهر')
        self.assertTrue(choices[0]['is_today'])
        self.assertEqual(choices[0]['weekday'], 'پنج‌شنبه')
        self.assertEqual(choices[1]['label'], 'جمعه ۱ آبان')
        self.assertFalse(choices[1]['is_today'])
        self.assertEqual(choices[-1]['value'], (TODAY + datetime.timedelta(days=30)).isoformat())

    def test_default_date_moves_to_tomorrow_late_at_night(self):
        late = datetime.datetime(2026, 10, 22, 22, 0, tzinfo=TEHRAN)
        self.assertEqual(ReservationForm(now=late).initial['date'], TOMORROW.isoformat())
        self.assertEqual(ReservationForm(now=NOW).initial['date'], TODAY.isoformat())


class PhoneNormalisationTests(TestCase):
    def test_valid_numbers(self):
        cases = {
            '09121234567': '09121234567',
            '۰۹۱۲ ۱۲۳ ۴۵۶۷': '09121234567',
            '٠٩١٢-١٢٣-٤٥٦٧': '09121234567',
            '+98 912 123 4567': '09121234567',
            '00989121234567': '09121234567',
            '989121234567': '09121234567',
            '9121234567': '09121234567',
            '041-36688554': '04136688554',
            '۰۴۱-۳۶۶۸۸۵۵۴': '04136688554',
            '+984136688554': '04136688554',
            '(041) 3668 8554': '04136688554',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), expected)

    def test_invalid_numbers(self):
        for raw in ('', '123', '0912123456', '091212345678', '00121234567', 'abc09121234567',
                    '+1 202 555 0100', '36688554'):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_phone(raw))


class ReservationFormTests(TestCase):
    def setUp(self):
        cache.clear()

    def make(self, ip='10.0.0.1', now=NOW, **overrides):
        return ReservationForm(form_data(**overrides), ip=ip, now=now)

    def test_valid_and_saved(self):
        form = self.make(phone='۰۹۱۲ ۱۲۳ ۴۵۶۷', guests='۴', date='۲۰۲۶-۱۰-۲۳', time='۲۰:۰۰')
        self.assertTrue(form.is_valid(), form.errors)
        reservation = form.save()
        self.assertEqual(reservation.phone, '09121234567')
        self.assertEqual(reservation.guests, 4)
        self.assertEqual(reservation.date, TOMORROW)
        self.assertEqual(reservation.time, datetime.time(20, 0))
        self.assertEqual(reservation.ip_address, '10.0.0.1')
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertEqual(len(reservation.code), 6)
        self.assertTrue(set(reservation.code) <= set(CODE_ALPHABET))
        self.assertFalse(set('0O1I') & set(reservation.code))

    def test_required_fields_have_persian_messages(self):
        form = ReservationForm({}, now=NOW)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['name'], [MESSAGES['name_required']])
        self.assertEqual(form.errors['phone'], [MESSAGES['phone_required']])
        self.assertEqual(form.errors['date'], [MESSAGES['date_required']])
        self.assertEqual(form.errors['time'], [MESSAGES['time_required']])
        self.assertEqual(form.errors['guests'], [MESSAGES['guests_required']])

    def test_name_rules(self):
        self.assertEqual(self.make(name=' ا ').errors['name'], [MESSAGES['name_short']])
        form = self.make(name='  علی   رضایی ')
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['name'], 'علی رضایی')

    def test_phone_rules(self):
        self.assertEqual(self.make(phone='12345').errors['phone'], [MESSAGES['phone_invalid']])
        form = self.make(phone='+98 41 3668 8554')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['phone'], '04136688554')

    def test_date_window(self):
        yesterday = TODAY - datetime.timedelta(days=1)
        last = TODAY + datetime.timedelta(days=30)
        too_far = TODAY + datetime.timedelta(days=31)
        self.assertEqual(self.make(date=yesterday.isoformat()).errors['date'], [MESSAGES['date_range']])
        self.assertEqual(self.make(date=too_far.isoformat()).errors['date'], [MESSAGES['date_range']])
        self.assertTrue(self.make(date=last.isoformat()).is_valid())
        self.assertEqual(self.make(date='1405/07/30').errors['date'], [MESSAGES['date_invalid']])

    def test_time_must_be_a_slot(self):
        for bad in ('11:30', '23:00', '20:15', '25:00', 'evening'):
            with self.subTest(time=bad):
                self.assertIn('time', self.make(time=bad).errors)
        self.assertTrue(self.make(time='12:00').is_valid())
        self.assertTrue(self.make(time='22:30').is_valid())

    def test_today_needs_an_hour_of_notice(self):
        today = TODAY.isoformat()
        self.assertEqual(self.make(date=today, time='13:00').errors['time'], [MESSAGES['time_too_soon']])
        self.assertEqual(self.make(date=today, time='16:00').errors['time'], [MESSAGES['time_too_soon']])
        self.assertTrue(self.make(date=today, time='16:30').is_valid())
        # The same early slot is fine tomorrow.
        self.assertTrue(self.make(time='12:00').is_valid())

    def test_guest_bounds(self):
        self.assertEqual(self.make(guests='0').errors['guests'], [MESSAGES['guests_min']])
        self.assertEqual(self.make(guests='21').errors['guests'], [MESSAGES['guests_max']])
        self.assertEqual(self.make(guests='چند').errors['guests'], [MESSAGES['guests_invalid']])
        self.assertTrue(self.make(guests='1').is_valid())
        self.assertTrue(self.make(guests='۲۰').is_valid())

    def test_occasion_and_notes(self):
        self.assertTrue(self.make(occasion='birthday', notes='  صندلی کودک  ').is_valid())
        self.assertIn('occasion', self.make(occasion='wedding').errors)
        self.assertIn('notes', self.make(notes='x' * 501).errors)

    def test_honeypot(self):
        form = self.make(website='http://spam.example')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors(), [MESSAGES['spam']])

    def test_rate_limit(self):
        for _ in range(5):
            form = self.make()
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        form = self.make()
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors(), [MESSAGES['rate_limited']])
        # Other visitors are not affected.
        self.assertTrue(self.make(ip='10.0.0.2').is_valid())

    def test_rate_limit_counts_only_the_last_hour(self):
        for _ in range(5):
            self.make(ip='10.0.0.9').save()
        self.assertFalse(self.make(ip='10.0.0.9').is_valid())
        Reservation.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=61))
        self.assertTrue(self.make(ip='10.0.0.9').is_valid())

    def test_phone_rejects_non_persian_unicode_digits(self):
        self.assertIsNone(normalize_phone('09' + '१२३४५६७८९'))
        self.assertIn('phone', self.make(phone='09' + '१२३४५६७८९').errors)

    def test_widget_attrs(self):
        form = ReservationForm(now=NOW)
        self.assertEqual(form.fields['name'].widget.attrs['autocomplete'], 'name')
        phone = form.fields['phone'].widget.attrs
        self.assertEqual((phone['inputmode'], phone['dir'], phone['autocomplete']), ('tel', 'ltr', 'tel'))
        guests = form.fields['guests'].widget.attrs
        self.assertEqual((guests['min'], guests['max']), (1, 20))
        self.assertIn('website', form.fields)


def _future_slot_data(**overrides):
    """Data valid regardless of the real current time (tomorrow evening)."""
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    return form_data(date=tomorrow.isoformat(), **overrides)


class ReservationViewTests(TestCase):
    """View behaviour that does not need the frontend templates."""

    def setUp(self):
        cache.clear()

    def test_successful_post_redirects_and_stores_code_in_session(self):
        response = self.client.post(reverse('reservations:create'), _future_slot_data())
        reservation = Reservation.objects.get()
        self.assertRedirects(
            response, reverse('reservations:done', args=[reservation.code]), fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session['reservation_codes'], [reservation.code])
        self.assertEqual(reservation.ip_address, '127.0.0.1')

    def test_done_page_requires_session(self):
        reservation = Reservation.objects.create(
            name='x y', phone='09121234567', date=timezone.localdate(), time=datetime.time(20), guests=2,
        )
        response = self.client.get(reverse('reservations:done', args=[reservation.code]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('reservations:done', args=['ABCDEF']))
        self.assertEqual(response.status_code, 404)

    @override_settings(RESERVATION_NOTIFY_EMAIL='owner@example.com')
    def test_notification_email(self):
        self.client.post(reverse('reservations:create'), _future_slot_data())
        self.assertEqual(len(mail.outbox), 1)
        reservation = Reservation.objects.get()
        self.assertIn(reservation.code, mail.outbox[0].subject)
        self.assertIn('09121234567', mail.outbox[0].body)

    def test_no_email_without_setting(self):
        self.client.post(reverse('reservations:create'), _future_slot_data())
        self.assertEqual(len(mail.outbox), 0)

    def test_x_forwarded_for_ignored_by_default(self):
        self.client.post(reverse('reservations:create'), _future_slot_data(),
                         HTTP_X_FORWARDED_FOR='1.2.3.4')
        self.assertEqual(Reservation.objects.get().ip_address, '127.0.0.1')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_x_forwarded_for_uses_the_entry_added_by_our_proxy(self):
        # The visitor can prepend anything; only the rightmost hop is trusted.
        self.client.post(reverse('reservations:create'), _future_slot_data(),
                         HTTP_X_FORWARDED_FOR='6.6.6.6, 1.2.3.4')
        self.assertEqual(Reservation.objects.get().ip_address, '1.2.3.4')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_spoofed_forwarded_for_cannot_dodge_rate_limit(self):
        for i in range(6):
            self.client.post(reverse('reservations:create'), _future_slot_data(),
                             HTTP_X_FORWARDED_FOR=f'evil{i}, 1.2.3.4')
        self.assertEqual(Reservation.objects.count(), 5)

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_invalid_forwarded_ip_is_not_stored(self):
        self.client.post(reverse('reservations:create'), _future_slot_data(),
                         HTTP_X_FORWARDED_FOR='not-an-ip')
        self.assertIsNone(Reservation.objects.get().ip_address)


class ReservationPageTests(TestCase):
    """Rendered reservation pages (need reservations/templates from the frontend)."""

    def setUp(self):
        cache.clear()

    def test_get_has_choices(self):
        response = self.client.get(reverse('reservations:create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reservations/reserve.html')
        self.assertEqual(len(response.context['date_choices']), 31)
        self.assertEqual(len(response.context['time_choices']), 22)
        self.assertIsInstance(response.context['form'], ReservationForm)
        self.assertContains(response, 'name="website"')

    def test_invalid_post_shows_errors(self):
        response = self.client.post(reverse('reservations:create'), _future_slot_data(phone='123'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MESSAGES['phone_invalid'])
        self.assertFalse(Reservation.objects.exists())

    def test_done_page_with_session(self):
        response = self.client.post(reverse('reservations:create'), _future_slot_data(), follow=True)
        reservation = Reservation.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reservations/done.html')
        self.assertEqual(response.context['reservation'], reservation)
        self.assertContains(response, reservation.code)

    def test_rate_limit_through_the_view(self):
        for _ in range(5):
            self.client.post(reverse('reservations:create'), _future_slot_data())
        response = self.client.post(reverse('reservations:create'), _future_slot_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, MESSAGES['rate_limited'])
        self.assertEqual(Reservation.objects.count(), 5)

    def test_disabled_reservations(self):
        site = SiteSettings.load()
        site.reservations_enabled = False
        site.save()
        response = self.client.get(reverse('reservations:create'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['reservations_enabled'])
        self.assertContains(response, 'tel:+984136688554')
        response = self.client.post(reverse('reservations:create'), _future_slot_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Reservation.objects.exists())


class ReservationModelTests(TestCase):
    def test_code_is_unique_even_on_collision(self):
        first = Reservation.objects.create(
            name='a b', phone='09121234567', date=TODAY, time=datetime.time(20), guests=2,
        )
        codes = iter([first.code, 'ZZZZZZ'])
        with mock.patch('reservations.models.generate_code', side_effect=lambda: next(codes)):
            second = Reservation.objects.create(
                name='c d', phone='09121234567', date=TODAY, time=datetime.time(20), guests=2,
            )
        self.assertEqual(second.code, 'ZZZZZZ')
        self.assertEqual(str(second), 'ZZZZZZ — c d')

    def test_code_retried_when_a_concurrent_insert_wins(self):
        Reservation.objects.create(
            code='AAAAAA', name='a b', phone='09121234567', date=TODAY, time=datetime.time(20), guests=2,
        )
        # The existence check misses the clash (as in a race); the insert must retry.
        codes = iter(['AAAAAA', 'BBBBBB'])
        with mock.patch.object(Reservation, '_unique_code', side_effect=lambda: next(codes)):
            second = Reservation.objects.create(
                name='c d', phone='09121234567', date=TODAY, time=datetime.time(20), guests=2,
            )
        self.assertEqual(second.code, 'BBBBBB')


class ReservationAdminTests(TestCase):
    """Staff side: phone normalisation, Persian-digit search, default list, Jalali pickers."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.user = get_user_model().objects.create_superuser('staff', 's@example.com', 'x-Strong-Pass-1')
        today = timezone.localdate()
        cls.upcoming = Reservation.objects.create(
            name='مهمان آینده', phone='09141234567', date=today + datetime.timedelta(days=2),
            time=datetime.time(20, 0), guests=3,
        )
        cls.old = Reservation.objects.create(
            name='مهمان قدیمی', phone='09351112233', date=today - datetime.timedelta(days=10),
            time=datetime.time(13, 0), guests=2, status=Reservation.Status.SEATED,
        )
        cls.older = Reservation.objects.create(
            name='مهمان خیلی قدیمی', phone='09351112244', date=today - datetime.timedelta(days=20),
            time=datetime.time(13, 0), guests=2, status=Reservation.Status.SEATED,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.changelist = reverse('admin:reservations_reservation_changelist')

    def _add_data(self, **overrides):
        data = {
            'status': 'confirmed', 'date': (timezone.localdate() + datetime.timedelta(days=1)).isoformat(),
            'time': '20:30', 'guests': '4', 'occasion': '', 'name': '  علی   رضایی ',
            'phone': '۰۹۱۲ ۳۴۵ ۶۷۸۹', 'notes': '', 'staff_note': '',
        }
        data.update(overrides)
        return data

    def test_bare_list_opens_on_upcoming(self):
        response = self.client.get(self.changelist)
        self.assertRedirects(response, f'{self.changelist}?when=upcoming')
        response = self.client.get(self.changelist, {'when': 'upcoming'})
        self.assertContains(response, self.upcoming.code)
        self.assertNotContains(response, self.old.code)
        self.assertContains(response, 'sr-tab is-selected')
        everything = self.client.get(self.changelist, {'when': 'all'})
        self.assertEqual(everything.context['cl'].result_count, 3)
        past = self.client.get(self.changelist, {'when': 'past'})
        self.assertEqual([r.pk for r in past.context['cl'].result_list], [self.old.pk, self.older.pk])

    def test_admin_phone_is_normalised(self):
        response = self.client.post(reverse('admin:reservations_reservation_add'), self._add_data())
        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get(phone='09123456789')
        self.assertEqual(reservation.name, 'علی رضایی')
        self.assertEqual(reservation.time, datetime.time(20, 30))

    def test_admin_rejects_invalid_phone(self):
        response = self.client.post(reverse('admin:reservations_reservation_add'), self._add_data(phone='abc'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'شمارهٔ تماس معتبر نیست')

    def test_search_with_persian_digits_and_international_format(self):
        for term in ('۰۹۱۴۱۲۳۴۵۶۷', '+98 914 123 4567', '۴۵۶۷'):
            with self.subTest(term=term):
                response = self.client.get(self.changelist, {'q': term, 'when': 'all'})
                self.assertEqual([r.pk for r in response.context['cl'].result_list], [self.upcoming.pk])

    def test_add_form_uses_jalali_dates_and_hhmm_slots(self):
        response = self.client.get(reverse('admin:reservations_reservation_add'))
        html = response.content.decode()
        self.assertIn('<select name="date"', html)
        self.assertIn('(امروز)', html)
        self.assertIn('<optgroup label="', html)
        self.assertIn('<option value="20:30">۲۰:۳۰</option>', html)
        self.assertNotIn('vDateField', html)
        self.assertNotIn('date-hierarchy', self.client.get(self.changelist, {'when': 'all'}).content.decode())

    def test_change_form_keeps_out_of_range_values_and_shows_jalali_created(self):
        self.older.time = datetime.time(11, 15)
        self.older.date = timezone.localdate() - datetime.timedelta(days=200)
        self.older.save()
        response = self.client.get(reverse('admin:reservations_reservation_change', args=[self.older.pk]))
        html = response.content.decode()
        self.assertIn(f'<option value="{self.older.date.isoformat()}" selected>', html)
        self.assertIn('<option value="11:15" selected>', html)
        self.assertIn('زمان ثبت', html)
        self.assertIn('ساعت ', html)
