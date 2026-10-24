"""
Jalali (Solar Hijri / Persian) calendar conversion.

Implements the well-known Borkowski "breaks" algorithm (as used by jalaali-js),
which matches the official Iranian calendar for Jalali years -61..3177.
Conversions go through Python's proleptic Gregorian ordinal, so no extra
Gregorian arithmetic is needed.
"""

import datetime

from django.utils import timezone

__all__ = [
    'MONTH_NAMES',
    'WEEKDAY_NAMES',
    'gregorian_to_jalali',
    'jalali_to_gregorian',
    'is_jalali_leap',
    'jalali_month_length',
    'weekday_name',
    'to_jalali',
    'format_jalali',
    'today_jalali',
    'persian_digits',
]

MONTH_NAMES = (
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
)

# Persian week starts on Saturday.
WEEKDAY_NAMES = ('شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه')

_BREAKS = (
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
    1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178,
)

_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def persian_digits(value):
    """Return ``str(value)`` with ASCII digits replaced by Persian digits."""
    return str(value).translate(_PERSIAN_DIGITS)


def _div(a, b):
    """Integer division truncating toward zero (like JavaScript's ``~~(a / b)``)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _mod(a, b):
    return a - _div(a, b) * b


def _jal_cal(jy):
    """Return ``(leap, gregorian_year, march_day)`` for Jalali year ``jy``.

    ``leap`` is 0 for a leap year; ``march_day`` is the day in March of the
    Gregorian year ``jy + 621`` on which 1 Farvardin falls.
    """
    if jy < _BREAKS[0] or jy >= _BREAKS[-1]:
        raise ValueError(f'Jalali year {jy} is out of the supported range.')
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, gy, march


def is_jalali_leap(jy):
    """True when Jalali year ``jy`` has 30 days in Esfand."""
    return _jal_cal(jy)[0] == 0


def jalali_month_length(jy, jm):
    if not 1 <= jm <= 12:
        raise ValueError('Jalali month must be in 1..12.')
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_jalali_leap(jy) else 29


def _jalali_to_ordinal(jy, jm, jd):
    _, gy, march = _jal_cal(jy)
    first_day = datetime.date(gy, 3, march).toordinal()
    return first_day + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1


def jalali_to_gregorian(jy, jm, jd):
    """Convert a Jalali date to a Gregorian ``(year, month, day)`` tuple."""
    if not 1 <= jd <= jalali_month_length(jy, jm):
        raise ValueError(f'Invalid Jalali date {jy}/{jm}/{jd}.')
    d = datetime.date.fromordinal(_jalali_to_ordinal(jy, jm, jd))
    return d.year, d.month, d.day


def gregorian_to_jalali(gy, gm, gd):
    """Convert a Gregorian date to a Jalali ``(year, month, day)`` tuple."""
    ordinal = datetime.date(gy, gm, gd).toordinal()
    jy = gy - 621
    leap, _, march = _jal_cal(jy)
    k = ordinal - datetime.date(gy, 3, march).toordinal()
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1


def _as_date(value):
    """Coerce a date/datetime to a local ``date`` (aware datetimes use Asia/Tehran)."""
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    if isinstance(value, datetime.date):
        return value
    raise TypeError(f'Expected a date or datetime, got {type(value).__name__}.')


def weekday_name(value):
    """Persian weekday name for a Gregorian date (``date.weekday()`` is Monday=0)."""
    return WEEKDAY_NAMES[(_as_date(value).weekday() + 2) % 7]


def to_jalali(value):
    """``(jy, jm, jd)`` for a date or datetime."""
    d = _as_date(value)
    return gregorian_to_jalali(d.year, d.month, d.day)


def format_jalali(value, long=False, with_year=True, digits=True):
    """Human-readable Persian date.

    >>> format_jalali(datetime.date(2026, 10, 23))
    '۱ آبان ۱۴۰۵'
    >>> format_jalali(datetime.date(2026, 10, 22), long=True)
    'پنج‌شنبه ۳۰ مهر ۱۴۰۵'

    Dates outside the supported Jalali range fall back to ISO format rather
    than raising, so one odd date typed in the admin can't break a page.
    """
    try:
        jy, jm, jd = to_jalali(value)
    except ValueError:
        return value.isoformat()
    parts = [str(jd), MONTH_NAMES[jm - 1]]
    if with_year:
        parts.append(str(jy))
    text = ' '.join(parts)
    if long:
        text = f'{weekday_name(value)} {text}'
    return persian_digits(text) if digits else text


def today_jalali():
    """Today's Jalali ``(jy, jm, jd)`` in the site's time zone."""
    return to_jalali(timezone.localdate())
