"""Admin helpers.

* ``{% saray_dashboard as dash %}`` — numbers and lists for the dashboard.
  Every card counts exactly the rows its link shows (shared definitions live
  in ``reservations.admin``: ``when_range``/``filter_when``/``active``).
* ``{{ results|sr_labelled:result_headers }}`` — adds ``data-label`` to each
  changelist cell so phones can show rows as labelled cards.
"""

import datetime
import re

from django import template
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.safestring import mark_safe

from saray_menu.jalali import format_jalali, persian_digits
from saray_menu.models import MenuItem

register = template.Library()


def _guests(queryset):
    return queryset.aggregate(total=Sum('guests'))['total'] or 0


def _rows(queryset, can_change, quick_url_name):
    """Reservations for the dashboard tables, with the one-tap buttons each may show."""
    from reservations.models import Reservation

    status = Reservation.Status
    rows = []
    for r in queryset.order_by('time', 'id'):
        buttons = []
        if can_change:
            if r.status == status.PENDING:
                buttons.append((status.CONFIRMED, 'تایید', 'confirm'))
            if r.status in (status.PENDING, status.CONFIRMED):
                buttons.append((status.SEATED, 'حاضر شد', 'seated'))
                buttons.append((status.CANCELLED, 'لغو', 'cancel'))
        rows.append({
            'obj': r,
            'quick_url': reverse(quick_url_name, args=[r.pk]),
            'buttons': [{'status': s, 'label': label, 'kind': kind} for s, label, kind in buttons],
        })
    return rows


@register.simple_tag(takes_context=True)
def saray_dashboard(context):
    """Numbers for the cards at the top of the admin index page.

    Sections the current user may not view are returned as ``None``.
    """
    from reservations.admin import active, filter_when, when_range
    from reservations.models import Reservation

    request = context.get('request')
    user = getattr(request, 'user', None)
    today = timezone.localdate()
    dash = {
        'today_label': format_jalali(today, long=True),
        'reservations': None,
        'menu': None,
    }

    if user is not None and user.has_perm('reservations.view_reservation'):
        changelist = reverse('admin:reservations_reservation_changelist')
        can_change = user.has_perm('reservations.change_reservation')
        everything = Reservation.objects.all()
        todays = active(filter_when(everything, 'today', today))
        tomorrows = active(filter_when(everything, 'tomorrow', today))
        week = active(filter_when(everything, 'week', today))
        pending = filter_when(everything, 'upcoming', today).filter(status=Reservation.Status.PENDING)
        today_rows = _rows(todays, can_change, 'admin:reservations_reservation_quick_status')
        _, week_last = when_range('week', today)
        dash['reservations'] = {
            'today': today_rows,
            'today_count': persian_digits(len(today_rows)),
            'today_guests': persian_digits(sum(row['obj'].guests for row in today_rows)),
            'tomorrow': _rows(tomorrows, can_change, 'admin:reservations_reservation_quick_status'),
            'tomorrow_label': format_jalali(today + datetime.timedelta(days=1), long=True),
            'pending_count': persian_digits(pending.count()),
            'week_count': persian_digits(week.count()),
            'week_guests': persian_digits(_guests(week)),
            'week_until': format_jalali(week_last, long=True, with_year=False),
            'today_url': f'{changelist}?when=today&status=active',
            'tomorrow_url': f'{changelist}?when=tomorrow&status=active',
            'pending_url': f'{changelist}?when=upcoming&status=pending',
            'week_url': f'{changelist}?when=week&status=active',
            'add_url': reverse('admin:reservations_reservation_add'),
            'can_change': can_change,
        }

    if user is not None and user.has_perm('saray_menu.view_menuitem'):
        changelist = reverse('admin:saray_menu_menuitem_changelist')
        total = MenuItem.objects.count()
        available = MenuItem.objects.filter(is_available=True).count()
        dash['menu'] = {
            'total': persian_digits(total),
            'available': persian_digits(available),
            'unavailable': persian_digits(total - available),
            'url': changelist,
            'unavailable_url': f'{changelist}?is_available__exact=0',
        }
    return dash


_CELL_OPEN = re.compile(r'^\s*<(td|th)\b')


@register.filter
def sr_labelled(results, headers):
    """Yield changelist rows whose cells carry ``data-label="<column title>"``."""
    titles = [escape(strip_tags(str(h.get('text', ''))).strip()) for h in headers]
    for row in results:
        cells = []
        for index, cell in enumerate(row):
            html = str(cell)
            title = titles[index] if index < len(titles) else ''
            if title:
                html = _CELL_OPEN.sub(lambda m: f'<{m.group(1)} data-label="{title}"', html, count=1)
            cells.append(mark_safe(html))
        yield {'cells': cells, 'form': getattr(row, 'form', None), 'length': len(row)}
