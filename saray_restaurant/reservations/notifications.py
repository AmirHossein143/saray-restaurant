"""Optional email notification for new reservations (``RESERVATION_NOTIFY_EMAIL``)."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from saray_menu.jalali import format_jalali

logger = logging.getLogger(__name__)


def notify_new_reservation(reservation):
    recipient = getattr(settings, 'RESERVATION_NOTIFY_EMAIL', '')
    if not recipient:
        return False
    lines = [
        f'کد رزرو: {reservation.code}',
        f'نام: {reservation.name}',
        f'تلفن: {reservation.phone}',
        f'تاریخ: {format_jalali(reservation.date, long=True)} ({reservation.date:%Y-%m-%d})',
        f'ساعت: {reservation.time:%H:%M}',
        f'تعداد نفرات: {reservation.guests}',
    ]
    if reservation.occasion:
        lines.append(f'مناسبت: {reservation.get_occasion_display()}')
    if reservation.notes:
        lines.append(f'توضیحات: {reservation.notes}')
    try:
        sent = send_mail(
            subject=f'رزرو جدید {reservation.code} — {reservation.name}',
            message='\n'.join(lines),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001 - a notification must never break a booking
        logger.exception('Reservation notification failed')
        return False
    return bool(sent)
