"""Persian admin for reservations.

* The list opens on upcoming reservations (today onward) with quick tabs for
  today / tomorrow / 7 days / past / all, and a status filter that includes
  "active" (everything except cancelled and no-show) — the same definitions
  the dashboard cards use, so their numbers always match the linked lists.
* Dates are picked from a Jalali-labelled list and times from HH:MM slots; no
  Gregorian calendar anywhere.
* Phone numbers are normalised (Persian digits, +98, spaces) and can be
  searched with Persian digits.
* Small POST endpoint for the dashboard's one-tap status buttons.
"""

import datetime

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme

from saray_menu.admin import PersianMessagesMixin, jalali_datetime
from saray_menu.jalali import MONTH_NAMES, format_jalali, persian_digits, to_jalali
from saray_menu.models import SiteSettings
from saray_menu.utils import ascii_digits

from .forms import normalize_phone, time_slots
from .models import MAX_GUESTS, MIN_GUESTS, Reservation

# --------------------------------------------------------------------------
# Shared definitions (also used by the dashboard in saray_menu.templatetags.saray_admin)
# --------------------------------------------------------------------------

#: "This week" everywhere in the admin = today and the next six days.
WEEK_DAYS = 7
#: Reservations that still matter for the kitchen and the floor.
INACTIVE_STATUSES = (Reservation.Status.CANCELLED, Reservation.Status.NO_SHOW)
#: Statuses the dashboard's one-tap buttons may set.
QUICK_STATUSES = (Reservation.Status.CONFIRMED, Reservation.Status.SEATED, Reservation.Status.CANCELLED)

ADMIN_DATE_DAYS_BACK = 30
ADMIN_DATE_DAYS_AHEAD = 60

PHONE_INVALID = 'شمارهٔ تماس معتبر نیست. نمونهٔ درست: ۰۹۱۲۳۴۵۶۷۸۹ یا ۰۴۱۳۶۶۸۸۵۵۴'


def when_range(key, today=None):
    """``(first, last)`` dates for a WhenFilter value (``None`` = open-ended)."""
    today = today or timezone.localdate()
    one_day = datetime.timedelta(days=1)
    return {
        'today': (today, today),
        'tomorrow': (today + one_day, today + one_day),
        'week': (today, today + datetime.timedelta(days=WEEK_DAYS - 1)),
        'upcoming': (today, None),
        'past': (None, today - one_day),
    }.get(key)


def filter_when(queryset, key, today=None):
    bounds = when_range(key, today)
    if bounds is None:
        return queryset
    first, last = bounds
    if first is not None:
        queryset = queryset.filter(date__gte=first)
    if last is not None:
        queryset = queryset.filter(date__lte=last)
    return queryset


def active(queryset):
    return queryset.exclude(status__in=INACTIVE_STATUSES)


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------


class WhenFilter(admin.SimpleListFilter):
    """Quick date ranges in the restaurant's local time.

    There is no implicit "all": the bare list redirects to ``?when=upcoming``,
    so "همه" is an explicit ``?when=all``.
    """

    title = 'زمان رزرو'
    parameter_name = 'when'
    DEFAULT = 'upcoming'

    def lookups(self, request, model_admin):
        return (
            ('upcoming', 'از امروز به بعد'),
            ('today', 'امروز'),
            ('tomorrow', 'فردا'),
            ('week', '۷ روز آینده (از امروز)'),
            ('past', 'گذشته'),
            ('all', 'همه'),
        )

    def choices(self, changelist):
        choices = list(super().choices(changelist))[1:]  # drop Django's implicit "All"
        if self.value() is None:
            choices[-1]['selected'] = True  # no date filter (e.g. a search) = "همه"
        return choices

    def queryset(self, request, queryset):
        return filter_when(queryset, self.value())


class StatusFilter(admin.SimpleListFilter):
    title = 'وضعیت'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (('active', 'فعال (بدون لغوشده‌ها و نیامده‌ها)'), *Reservation.Status.choices)

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'active':
            return active(queryset)
        if value in Reservation.Status.values:
            return queryset.filter(status=value)
        return queryset


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def _date_label(day, today):
    label = format_jalali(day, long=True, with_year=False)
    if day == today:
        return f'{label} (امروز)'
    if day == today + datetime.timedelta(days=1):
        return f'{label} (فردا)'
    return label


def date_choices(current=None, today=None):
    """Dates from 30 days ago to 60 days ahead, grouped by Jalali month."""
    today = today or timezone.localdate()
    days = [today + datetime.timedelta(days=n) for n in range(-ADMIN_DATE_DAYS_BACK, ADMIN_DATE_DAYS_AHEAD + 1)]
    if current and current not in days:
        days.append(current)
        days.sort()
    groups = {}
    for day in days:
        jy, jm, _ = to_jalali(day)
        group = f'{MONTH_NAMES[jm - 1]} {persian_digits(jy)}'
        groups.setdefault(group, []).append((day.isoformat(), _date_label(day, today)))
    return list(groups.items())


def admin_time_slots(current=None):
    """Every half hour while the restaurant is open, plus the online slots and ``current``."""
    site = SiteSettings.load()
    slots = set(time_slots())
    start = datetime.datetime.combine(datetime.date.min, site.opens_at)
    end = datetime.datetime.combine(datetime.date.min, site.closes_at)
    minutes = start.minute
    if minutes % 30:
        start += datetime.timedelta(minutes=30 - minutes % 30)
    while start < end:
        slots.add(start.time())
        start += datetime.timedelta(minutes=30)
    if current:
        slots.add(current.replace(second=0, microsecond=0))
    return sorted(slots)


class ReservationAdminForm(forms.ModelForm):
    date = forms.TypedChoiceField(
        label='تاریخ', coerce=datetime.date.fromisoformat,
        error_messages={'required': 'لطفاً تاریخ رزرو را انتخاب کنید.',
                        'invalid_choice': 'تاریخ انتخاب‌شده معتبر نیست.'},
    )
    time = forms.TypedChoiceField(
        label='ساعت', coerce=lambda v: datetime.datetime.strptime(v, '%H:%M').time(),
        error_messages={'required': 'لطفاً ساعت رزرو را انتخاب کنید.',
                        'invalid_choice': 'ساعت انتخاب‌شده معتبر نیست.'},
    )
    guests = forms.TypedChoiceField(
        label='تعداد نفرات', coerce=int,
        choices=[(n, persian_digits(n)) for n in range(MIN_GUESTS, MAX_GUESTS + 1)],
        error_messages={'required': 'لطفاً تعداد نفرات را انتخاب کنید.'},
    )
    phone = forms.CharField(
        label='شماره تماس', max_length=30,
        widget=forms.TextInput(attrs={
            'dir': 'ltr', 'class': 'sr-ltr', 'inputmode': 'tel', 'autocomplete': 'off',
            'placeholder': '۰۹۱۲ ۳۴۵ ۶۷۸۹',
        }),
        help_text='موبایل یا تلفن ثابت؛ با رقم فارسی یا انگلیسی.',
        error_messages={'required': 'لطفاً شمارهٔ تماس را وارد کنید.'},
    )

    class Meta:
        model = Reservation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        current_date = self.instance.date if self.instance.pk else None
        current_time = self.instance.time if self.instance.pk else None
        self.fields['date'].choices = [('', '— روز را انتخاب کنید —'), *date_choices(current_date, today)]
        self.fields['time'].choices = [('', '— ساعت —')] + [
            (f'{t:%H:%M}', persian_digits(f'{t:%H:%M}')) for t in admin_time_slots(current_time)
        ]
        if self.instance.pk:
            self.initial['date'] = current_date.isoformat()
            self.initial['time'] = f'{current_time:%H:%M}'
        else:
            self.initial.setdefault('date', today.isoformat())
            self.initial.setdefault('guests', 2)
            # Bookings typed in by staff (usually by phone) are confirmed already.
            self.initial.setdefault('status', Reservation.Status.CONFIRMED)

    def clean_name(self):
        return ' '.join(self.cleaned_data['name'].split())

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data['phone'])
        if phone is None:
            raise forms.ValidationError(PHONE_INVALID, code='invalid')
        return phone


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------


@admin.register(Reservation)
class ReservationAdmin(PersianMessagesMixin, admin.ModelAdmin):
    form = ReservationAdminForm
    list_display = (
        'jalali_date', 'time_display', 'name', 'guests_display', 'phone_link',
        'status_badge', 'occasion_display', 'code',
    )
    list_display_links = ('name', 'code')
    list_filter = (WhenFilter, StatusFilter, 'occasion')
    search_fields = ('name', 'phone', 'code')
    search_help_text = 'جستجو با نام، شماره تماس (فارسی یا انگلیسی) یا کد رزرو.'
    list_per_page = 50
    actions = ('mark_confirmed', 'mark_seated', 'mark_cancelled', 'mark_no_show')
    readonly_fields = ('code', 'created_display', 'updated_display', 'ip_address')

    def get_fieldsets(self, request, obj=None):
        booking = ('status', 'date', 'time', 'guests', 'occasion')
        fieldsets = [
            ('رزرو', {'fields': (('code',) if obj else ()) + booking}),
            ('مهمان', {'fields': ('name', 'phone', 'notes')}),
            ('یادداشت داخلی', {'fields': ('staff_note',)}),
        ]
        if obj:
            fieldsets.append(('سوابق', {
                'fields': ('created_display', 'updated_display', 'ip_address'), 'classes': ('collapse',),
            }))
        return fieldsets

    # ----- list ---------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        # The bare list (menu link, breadcrumbs) opens on today and later.
        if request.method == 'GET' and not request.GET:
            return HttpResponseRedirect(f'{request.path}?{WhenFilter.parameter_name}={WhenFilter.DEFAULT}')
        extra_context = {**(extra_context or {}), 'sr_when_tabs': self._when_tabs(request)}
        return super().changelist_view(request, extra_context)

    def _when_tabs(self, request):
        current = request.GET.get(WhenFilter.parameter_name, 'all')
        params = request.GET.copy()
        params.pop('p', None)
        tabs = []
        for key, label in (('today', 'امروز'), ('tomorrow', 'فردا'), ('week', '۷ روز آینده'),
                           ('upcoming', 'همهٔ آینده'), ('past', 'گذشته'), ('all', 'همه')):
            params[WhenFilter.parameter_name] = key
            tabs.append({'label': label, 'url': f'?{params.urlencode()}', 'selected': key == current})
        return tabs

    def get_ordering(self, request):
        if request.GET.get(WhenFilter.parameter_name) == 'past':
            return ('-date', '-time')
        return ('date', 'time')

    def get_search_results(self, request, queryset, search_term):
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        term = ascii_digits(search_term).strip()
        extra_terms = set()
        if term != search_term.strip():
            extra_terms.add(term)
        digits = ''.join(ch for ch in term if ch.isdigit())
        if digits and len(digits) >= 4 and all(ch.isdigit() or ch in ' -+()' for ch in term):
            extra_terms.add(digits)
            phone = normalize_phone(term)
            if phone:
                extra_terms.add(phone)
        for extra in extra_terms - {search_term}:
            more, dup = super().get_search_results(request, queryset, extra)
            results = results | more
            may_have_duplicates = may_have_duplicates or dup
        return results, may_have_duplicates

    @admin.display(description='تاریخ', ordering='date')
    def jalali_date(self, obj):
        if not obj.date:
            return '—'
        label = format_html('<span class="sr-nowrap">{}</span>', format_jalali(obj.date, long=True))
        today = timezone.localdate()
        if obj.date == today:
            return format_html('{} <span class="sr-today">امروز</span>', label)
        if obj.date == today + datetime.timedelta(days=1):
            return format_html('{} <span class="sr-today sr-today--tomorrow">فردا</span>', label)
        return label

    @admin.display(description='مناسبت', ordering='occasion')
    def occasion_display(self, obj):
        return obj.get_occasion_display() if obj.occasion else '—'

    @admin.display(description='ساعت', ordering='time')
    def time_display(self, obj):
        return persian_digits(f'{obj.time:%H:%M}') if obj.time else '—'

    @admin.display(description='نفرات', ordering='guests')
    def guests_display(self, obj):
        return f'{persian_digits(obj.guests)} نفر'

    @admin.display(description='تلفن', ordering='phone')
    def phone_link(self, obj):
        return format_html('<a href="tel:{}" dir="ltr" class="sr-tel">{}</a>', obj.phone, obj.phone)

    @admin.display(description='وضعیت', ordering='status')
    def status_badge(self, obj):
        return format_html(
            '<span class="sr-badge sr-badge--{}">{}</span>', obj.status, obj.get_status_display(),
        )

    @admin.display(description='زمان ثبت')
    def created_display(self, obj):
        return jalali_datetime(obj.created_at)

    @admin.display(description='آخرین تغییر')
    def updated_display(self, obj):
        return jalali_datetime(obj.updated_at)

    # ----- actions ------------------------------------------------------

    def _set_status(self, request, queryset, status):
        count = queryset.update(status=status, updated_at=timezone.now())
        label = Reservation.Status(status).label
        self.message_user(
            request, f'وضعیت {persian_digits(count)} رزرو به «{label}» تغییر کرد.', messages.SUCCESS,
        )

    @admin.action(description='تایید رزروهای انتخاب‌شده')
    def mark_confirmed(self, request, queryset):
        self._set_status(request, queryset, Reservation.Status.CONFIRMED)

    @admin.action(description='لغو رزروهای انتخاب‌شده')
    def mark_cancelled(self, request, queryset):
        self._set_status(request, queryset, Reservation.Status.CANCELLED)

    @admin.action(description='علامت «حاضر شد»')
    def mark_seated(self, request, queryset):
        self._set_status(request, queryset, Reservation.Status.SEATED)

    @admin.action(description='علامت «نیامد»')
    def mark_no_show(self, request, queryset):
        self._set_status(request, queryset, Reservation.Status.NO_SHOW)

    # ----- one-tap status from the dashboard ----------------------------

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return [
            path(
                '<int:pk>/quick-status/',
                self.admin_site.admin_view(self.quick_status_view),
                name='%s_%s_quick_status' % info,
            ),
            *super().get_urls(),
        ]

    def quick_status_view(self, request, pk):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        obj = get_object_or_404(Reservation, pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        status = request.POST.get('status')
        if status not in QUICK_STATUSES:
            self.message_user(request, 'وضعیت درخواستی معتبر نیست.', messages.ERROR)
        elif obj.status != status:
            obj.status = status
            obj.save(update_fields=['status', 'updated_at'])
            self.log_change(request, obj, [{'changed': {'fields': ['وضعیت']}}])
            self.message_user(
                request,
                f'رزرو {obj.name} ({persian_digits(f"{obj.time:%H:%M}")}) «{obj.get_status_display()}» شد.',
                messages.SUCCESS,
            )
        next_url = request.POST.get('next') or reverse('admin:index')
        if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
            next_url = reverse('admin:index')
        return HttpResponseRedirect(next_url)
