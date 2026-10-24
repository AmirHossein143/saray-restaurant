import datetime

from django.test import SimpleTestCase

from saray_menu.jalali import (
    MONTH_NAMES,
    WEEKDAY_NAMES,
    format_jalali,
    gregorian_to_jalali,
    is_jalali_leap,
    jalali_month_length,
    jalali_to_gregorian,
    persian_digits,
    weekday_name,
)

KNOWN_PAIRS = [
    # (gregorian, jalali)
    ((2026, 3, 21), (1405, 1, 1)),
    ((2026, 10, 22), (1405, 7, 30)),
    ((2026, 10, 23), (1405, 8, 1)),
    ((2025, 3, 20), (1403, 12, 30)),  # 1403 is a leap year
    ((2025, 3, 21), (1404, 1, 1)),
    ((2024, 3, 20), (1403, 1, 1)),
    ((2024, 3, 19), (1402, 12, 29)),
    ((2021, 3, 20), (1399, 12, 30)),  # 1399 leap
    ((1979, 2, 11), (1357, 11, 22)),
    ((2000, 1, 1), (1378, 10, 11)),
]


class JalaliConversionTests(SimpleTestCase):
    def test_known_pairs(self):
        for g, j in KNOWN_PAIRS:
            with self.subTest(gregorian=g):
                self.assertEqual(gregorian_to_jalali(*g), j)
                self.assertEqual(jalali_to_gregorian(*j), g)

    def test_round_trip_over_a_century(self):
        day = datetime.date(1950, 1, 1)
        end = datetime.date(2060, 1, 1)
        while day < end:
            j = gregorian_to_jalali(day.year, day.month, day.day)
            self.assertEqual(jalali_to_gregorian(*j), (day.year, day.month, day.day))
            day += datetime.timedelta(days=1)

    def test_leap_years(self):
        self.assertTrue(is_jalali_leap(1403))
        self.assertTrue(is_jalali_leap(1399))
        self.assertFalse(is_jalali_leap(1404))
        self.assertFalse(is_jalali_leap(1405))
        self.assertEqual(jalali_month_length(1403, 12), 30)
        self.assertEqual(jalali_month_length(1404, 12), 29)
        self.assertEqual(jalali_month_length(1405, 1), 31)
        self.assertEqual(jalali_month_length(1405, 7), 30)

    def test_invalid_dates_rejected(self):
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1404, 12, 30)  # 1404 is not leap
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1404, 13, 1)

    def test_names(self):
        self.assertEqual(len(MONTH_NAMES), 12)
        self.assertEqual(MONTH_NAMES[7], 'آبان')
        self.assertEqual(WEEKDAY_NAMES[0], 'شنبه')
        self.assertEqual(weekday_name(datetime.date(2026, 10, 22)), 'پنج‌شنبه')
        self.assertEqual(weekday_name(datetime.date(2026, 10, 24)), 'شنبه')
        self.assertEqual(weekday_name(datetime.date(2026, 10, 23)), 'جمعه')

    def test_format(self):
        self.assertEqual(format_jalali(datetime.date(2026, 10, 23)), '۱ آبان ۱۴۰۵')
        self.assertEqual(
            format_jalali(datetime.date(2026, 10, 22), long=True), 'پنج‌شنبه ۳۰ مهر ۱۴۰۵',
        )
        self.assertEqual(
            format_jalali(datetime.date(2026, 10, 22), long=True, with_year=False), 'پنج‌شنبه ۳۰ مهر',
        )

    def test_aware_datetime_uses_tehran_time(self):
        # 2026-10-22 21:00 UTC is already 23 Oct (00:30) in Tehran.
        moment = datetime.datetime(2026, 10, 22, 21, 0, tzinfo=datetime.UTC)
        self.assertEqual(format_jalali(moment), '۱ آبان ۱۴۰۵')

    def test_persian_digits(self):
        self.assertEqual(persian_digits('12:30'), '۱۲:۳۰')
        self.assertEqual(persian_digits(1405), '۱۴۰۵')

    def test_out_of_range_dates_fall_back_to_iso(self):
        # A typo like year 3900 in the admin must not break list pages.
        self.assertEqual(format_jalali(datetime.date(3900, 1, 1)), '3900-01-01')
