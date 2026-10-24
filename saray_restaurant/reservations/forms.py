"""Reservation form with Persian validation messages.

Besides the model fields it validates:

* phone numbers typed with Persian/Arabic digits, spaces, dashes or +98;
* the booking window (today .. +30 days, Asia/Tehran);
* time slots (12:00–22:30 every 30 minutes; today only ≥ 60 minutes ahead);
* a honeypot field (``website``) and a per-IP hourly rate limit.
"""

import datetime
import re

from django import forms
from django.conf import settings
from django.utils import timezone

from saray_menu.jalali import MONTH_NAMES, format_jalali, persian_digits, to_jalali, weekday_name
from saray_menu.utils import ascii_digits

from .models import MAX_GUESTS, MIN_GUESTS, Reservation

BOOKING_WINDOW_DAYS = 30
FIRST_SLOT = datetime.time(12, 0)
LAST_SLOT = datetime.time(22, 30)
SLOT_MINUTES = 30
MIN_LEAD_MINUTES = 60
RATE_LIMIT_WINDOW = 60 * 60  # seconds

MESSAGES = {
    'name_required': 'لطفاً نام خود را وارد کنید.',
    'name_short': 'نام باید دست‌کم ۲ حرف باشد.',
    'name_long': 'نام حداکثر می‌تواند ۱۰۰ حرف باشد.',
    'phone_required': 'لطفاً شمارهٔ تماس خود را وارد کنید.',
    'phone_invalid': 'شمارهٔ تماس معتبر نیست. نمونهٔ درست: ۰۹۱۲۳۴۵۶۷۸۹ یا ۰۴۱۳۶۶۸۸۵۵۴',
    'date_required': 'لطفاً تاریخ رزرو را انتخاب کنید.',
    'date_invalid': 'تاریخ انتخاب‌شده معتبر نیست.',
    'date_range': 'رزرو فقط برای امروز تا ۳۰ روز آینده امکان‌پذیر است.',
    'time_required': 'لطفاً ساعت رزرو را انتخاب کنید.',
    'time_invalid': 'ساعت انتخاب‌شده معتبر نیست؛ رزرو بین ۱۲:۰۰ تا ۲۲:۳۰ و در نیم‌ساعت‌های کامل امکان‌پذیر است.',
    'time_too_soon': 'برای امروز، ساعت رزرو باید دست‌کم یک ساعت بعد از اکنون باشد؛ لطفاً ساعت دیگری انتخاب کنید.',
    'guests_required': 'لطفاً تعداد نفرات را وارد کنید.',
    'guests_invalid': 'تعداد نفرات باید یک عدد باشد.',
    'guests_min': 'تعداد نفرات دست‌کم ۱ نفر است.',
    'guests_max': 'برای مراسم بیش از ۲۰ نفر تماس بگیرید.',
    'notes_long': 'توضیحات حداکثر می‌تواند ۵۰۰ حرف باشد.',
    'occasion_invalid': 'مناسبت انتخاب‌شده معتبر نیست.',
    'spam': 'درخواست شما قابل ثبت نیست.',
    'rate_limited': (
        'از این دستگاه در یک ساعت گذشته رزروهای زیادی ثبت شده است؛ '
        'لطفاً کمی بعد دوباره تلاش کنید یا با رستوران تماس بگیرید.'
    ),
    'disabled': 'رزرو آنلاین در حال حاضر فعال نیست؛ لطفاً تماس بگیرید.',
}

# --------------------------------------------------------------------------
# Slots and choices
# --------------------------------------------------------------------------


def time_slots():
    """Bookable times: 12:00, 12:30, … 22:30."""
    slots = []
    current = datetime.datetime.combine(datetime.date.min, FIRST_SLOT)
    last = datetime.datetime.combine(datetime.date.min, LAST_SLOT)
    while current <= last:
        slots.append(current.time())
        current += datetime.timedelta(minutes=SLOT_MINUTES)
    return slots


def _now(now=None):
    return timezone.localtime(now) if now is not None else timezone.localtime()


def slot_is_bookable_today(slot, now=None):
    now = _now(now)
    earliest = now + datetime.timedelta(minutes=MIN_LEAD_MINUTES)
    slot_dt = datetime.datetime.combine(now.date(), slot, tzinfo=now.tzinfo)
    return slot_dt >= earliest


def booking_window(now=None):
    today = _now(now).date()
    return today, today + datetime.timedelta(days=BOOKING_WINDOW_DAYS)


def date_choices(now=None):
    """Today .. +30 days, labelled in Jalali with Persian digits.

    Each entry: ``{value, label, is_today, weekday, day, month}`` — e.g.
    ``{'value': '2026-10-22', 'label': 'پنج‌شنبه ۳۰ مهر', 'is_today': True, …}``.
    """
    first, last = booking_window(now)
    choices = []
    for offset in range((last - first).days + 1):
        day = first + datetime.timedelta(days=offset)
        _, jm, jd = to_jalali(day)
        choices.append({
            'value': day.isoformat(),
            'label': format_jalali(day, long=True, with_year=False),
            'is_today': offset == 0,
            'weekday': weekday_name(day),
            'day': persian_digits(jd),
            'month': MONTH_NAMES[jm - 1],
        })
    return choices


def time_choices(now=None):
    """``{value: '12:00', label: '۱۲:۰۰', available_today: bool}`` for every slot."""
    return [
        {
            'value': f'{slot:%H:%M}',
            'label': persian_digits(f'{slot:%H:%M}'),
            'available_today': slot_is_bookable_today(slot, now),
        }
        for slot in time_slots()
    ]


def default_date(now=None):
    """Today if a slot is still bookable, otherwise tomorrow."""
    today = _now(now).date()
    if any(slot_is_bookable_today(slot, now) for slot in time_slots()):
        return today
    return today + datetime.timedelta(days=1)


# --------------------------------------------------------------------------
# Phone numbers
# --------------------------------------------------------------------------

_PHONE_STRIP = re.compile(r'[\s\-‐-―().‌‎‏]')
_MOBILE = re.compile(r'^09[0-9]{9}$')
_LANDLINE = re.compile(r'^0[1-8][0-9]{9}$')


def normalize_phone(value):
    """Return ``09xxxxxxxxx`` / 11-digit landline, or ``None`` if not a valid Iranian number."""
    number = _PHONE_STRIP.sub('', ascii_digits(value or ''))
    if number.startswith('+98'):
        number = '0' + number[3:]
    elif number.startswith('0098'):
        number = '0' + number[4:]
    elif number.startswith('98') and len(number) == 12:
        number = '0' + number[2:]
    elif number.startswith('9') and len(number) == 10:
        number = '0' + number
    if _MOBILE.match(number) or _LANDLINE.match(number):
        return number
    return None


# --------------------------------------------------------------------------
# Rate limiting (per IP, sliding one-hour window, counted in the database so
# every worker process sees the same numbers)
# --------------------------------------------------------------------------


def rate_limit_reached(ip):
    if not ip:
        return False
    limit = getattr(settings, 'RESERVATION_RATE_LIMIT', 5)
    since = timezone.now() - datetime.timedelta(seconds=RATE_LIMIT_WINDOW)
    return Reservation.objects.filter(ip_address=ip, created_at__gte=since).count() >= limit


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


class ReservationForm(forms.ModelForm):
    # Fields whose input may contain Persian/Arabic digits.
    DIGIT_FIELDS = ('phone', 'date', 'time', 'guests')

    date = forms.DateField(
        label='تاریخ',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d'),
        error_messages={'required': MESSAGES['date_required'], 'invalid': MESSAGES['date_invalid']},
    )
    time = forms.TimeField(
        label='ساعت',
        input_formats=['%H:%M', '%H:%M:%S'],
        widget=forms.TimeInput(format='%H:%M'),
        error_messages={'required': MESSAGES['time_required'], 'invalid': MESSAGES['time_invalid']},
    )
    guests = forms.IntegerField(
        label='تعداد نفرات',
        min_value=MIN_GUESTS,
        max_value=MAX_GUESTS,
        widget=forms.NumberInput(attrs={'min': MIN_GUESTS, 'max': MAX_GUESTS, 'inputmode': 'numeric'}),
        error_messages={
            'required': MESSAGES['guests_required'],
            'invalid': MESSAGES['guests_invalid'],
            'min_value': MESSAGES['guests_min'],
            'max_value': MESSAGES['guests_max'],
        },
    )
    # Honeypot: hidden from people with CSS; bots tend to fill every field.
    website = forms.CharField(
        label='وب‌سایت',
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1'}),
    )

    class Meta:
        model = Reservation
        fields = ['name', 'phone', 'date', 'time', 'guests', 'occasion', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'autocomplete': 'name', 'maxlength': 100}),
            'phone': forms.TextInput(attrs={
                'inputmode': 'tel', 'dir': 'ltr', 'autocomplete': 'tel',
                'placeholder': '۰۹۱۲ ۳۴۵ ۶۷۸۹',
            }),
            'notes': forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
        }
        error_messages = {
            'name': {'required': MESSAGES['name_required'], 'max_length': MESSAGES['name_long']},
            'phone': {'required': MESSAGES['phone_required'], 'max_length': MESSAGES['phone_invalid']},
            'occasion': {'invalid_choice': MESSAGES['occasion_invalid']},
            'notes': {'max_length': MESSAGES['notes_long']},
        }

    def __init__(self, data=None, *args, ip=None, now=None, **kwargs):
        if data is not None:
            data = data.copy()
            for field in self.DIGIT_FIELDS:
                if field in data:
                    data[field] = ascii_digits(data[field]).strip()
        self.ip = ip
        self.now = _now(now)
        kwargs.setdefault('initial', {})
        kwargs['initial'].setdefault('date', default_date(self.now).isoformat())
        kwargs['initial'].setdefault('guests', 2)
        super().__init__(data, *args, **kwargs)
        self.fields['phone'].max_length = None  # length is checked after normalisation
        self.fields['phone'].validators = []

    def clean_name(self):
        name = ' '.join(self.cleaned_data['name'].split())
        if len(name) < 2:
            raise forms.ValidationError(MESSAGES['name_short'], code='min_length')
        return name

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if phone is None:
            raise forms.ValidationError(MESSAGES['phone_invalid'], code='invalid')
        return phone

    def clean_date(self):
        value = self.cleaned_data['date']
        first, last = booking_window(self.now)
        if not first <= value <= last:
            raise forms.ValidationError(MESSAGES['date_range'], code='out_of_range')
        return value

    def clean_time(self):
        value = self.cleaned_data['time']
        if value.replace(second=0, microsecond=0) != value or value not in time_slots():
            raise forms.ValidationError(MESSAGES['time_invalid'], code='invalid_slot')
        return value

    def clean_notes(self):
        return self.cleaned_data.get('notes', '').strip()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('website'):
            raise forms.ValidationError(MESSAGES['spam'], code='honeypot')
        day, slot = cleaned.get('date'), cleaned.get('time')
        if day and slot and day == self.now.date() and not slot_is_bookable_today(slot, self.now):
            self.add_error('time', forms.ValidationError(MESSAGES['time_too_soon'], code='too_soon'))
        if rate_limit_reached(self.ip):
            raise forms.ValidationError(MESSAGES['rate_limited'], code='rate_limited')
        return cleaned

    def save(self, commit=True):
        reservation = super().save(commit=False)
        reservation.ip_address = self.ip
        if commit:
            reservation.save()
        return reservation
