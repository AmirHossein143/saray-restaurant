"""Small text helpers shared by the menu and reservations apps."""

import ipaddress

from .jalali import persian_digits

__all__ = ['persian_digits', 'ascii_digits', 'group_thousands', 'client_ip']

# Persian (U+06F0..) and Arabic-Indic (U+0660..) digits → ASCII.
_ASCII_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '0123456789' * 2)

# Persian thousands separator (ARABIC THOUSANDS SEPARATOR, U+066C).
THOUSANDS_SEPARATOR = '٬'


def ascii_digits(value):
    """Return ``str(value)`` with Persian/Arabic-Indic digits converted to ASCII."""
    return str(value).translate(_ASCII_DIGITS)


def group_thousands(number):
    """``1250000`` → ``'۱٬۲۵۰٬۰۰۰'`` (Persian digits and separator)."""
    return persian_digits(f'{int(number):,}'.replace(',', THOUSANDS_SEPARATOR))


def client_ip(request):
    """Best-effort client IP address, or ``None``.

    Behind ``settings.TRUSTED_PROXY_COUNT`` reverse proxies, the address is the
    entry in X-Forwarded-For that the outermost trusted proxy appended (counted
    from the right). Entries further left are supplied by the client and are
    never trusted. Without proxies, REMOTE_ADDR is used.
    """
    from django.conf import settings

    ip = request.META.get('REMOTE_ADDR')
    proxies = getattr(settings, 'TRUSTED_PROXY_COUNT', 0)
    if proxies:
        hops = [h.strip() for h in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if h.strip()]
        if len(hops) >= proxies:
            ip = hops[-proxies]
    try:
        return str(ipaddress.ip_address(ip))
    except (TypeError, ValueError):
        return None
