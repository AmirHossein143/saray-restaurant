"""Online table reservation pages."""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from saray_menu.models import SiteSettings
from saray_menu.utils import client_ip

from .forms import MESSAGES, ReservationForm, date_choices, time_choices
from .models import Reservation
from .notifications import notify_new_reservation

SESSION_KEY = 'reservation_codes'
MAX_SESSION_CODES = 20


def _render(request, form, now, site, status=200):
    return render(request, 'reservations/reserve.html', {
        'form': form,
        'date_choices': date_choices(now),
        'time_choices': time_choices(now),
        'reservations_enabled': site.reservations_enabled,
        'disabled_message': MESSAGES['disabled'],
    }, status=status)


@require_http_methods(['GET', 'HEAD', 'POST'])
def create(request):
    now = timezone.localtime()
    ip = client_ip(request)
    site = SiteSettings.load()

    if not site.reservations_enabled:
        # The template shows a "please call us" panel instead of the form.
        form = ReservationForm(ip=ip, now=now)
        return _render(request, form, now, site, status=403 if request.method == 'POST' else 200)

    if request.method == 'POST':
        form = ReservationForm(request.POST, ip=ip, now=now)
        if form.is_valid():
            reservation = form.save()
            codes = [c for c in request.session.get(SESSION_KEY, []) if c != reservation.code]
            codes.append(reservation.code)
            request.session[SESSION_KEY] = codes[-MAX_SESSION_CODES:]
            notify_new_reservation(reservation)
            return redirect('reservations:done', code=reservation.code)
    else:
        form = ReservationForm(ip=ip, now=now)
    return _render(request, form, now, site)


def done(request, code):
    """Confirmation page — only for reservations made in this browser session."""
    code = code.upper()
    if code not in request.session.get(SESSION_KEY, []):
        raise Http404('Reservation not found')
    reservation = get_object_or_404(Reservation, code=code)
    return render(request, 'reservations/done.html', {'reservation': reservation})
