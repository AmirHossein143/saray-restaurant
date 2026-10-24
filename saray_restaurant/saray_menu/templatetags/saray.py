"""Template filters and tags for the Saray site: ``{% load saray %}``."""

import datetime
import json

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from saray_menu.jalali import format_jalali, persian_digits
from saray_menu.utils import group_thousands

register = template.Library()


def _to_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@register.filter
def fa_digits(value):
    """Convert ASCII digits to Persian digits: ``"12:30"`` → ``"۱۲:۳۰"``."""
    if value is None:
        return ''
    return persian_digits(value)


@register.filter
def toman(value):
    """Format a Toman price.

    ``250000`` → ``"۲۵۰ هزار تومان"``, ``250500`` → ``"۲۵۰٬۵۰۰ تومان"``, ``None`` → ``""``.
    """
    amount = _to_int(value)
    if amount is None:
        return ''
    if amount and amount % 1000 == 0:
        return f'{group_thousands(amount // 1000)} هزار تومان'
    return f'{group_thousands(amount)} تومان'


@register.filter
def price_short(value):
    """Price in thousands of Toman for compact display: ``250000`` → ``"۲۵۰"``.

    Amounts that are not a whole number of thousands keep one decimal
    (``250500`` → ``"۲۵۰٫۵"``).
    """
    amount = _to_int(value)
    if amount is None:
        return ''
    whole, rest = divmod(amount, 1000)
    text = group_thousands(whole)
    if rest:
        decimals = f'{rest / 1000:.3f}'[2:].rstrip('0')
        text += '٫' + persian_digits(decimals)
    return text


def _as_date(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


@register.filter
def jalali(value):
    """Date → ``"۱ آبان ۱۴۰۵"``."""
    value = _as_date(value)
    return format_jalali(value) if value else ''


@register.filter
def jalali_long(value):
    """Date → ``"پنج‌شنبه ۱ آبان ۱۴۰۵"``."""
    value = _as_date(value)
    return format_jalali(value, long=True) if value else ''


@register.filter
def thousands(value):
    """Group digits with the Persian separator: ``1250000`` → ``"۱٬۲۵۰٬۰۰۰"``."""
    amount = _to_int(value)
    return '' if amount is None else group_thousands(amount)


def restaurant_json_ld(site, request=None):
    """schema.org Restaurant data built only from what the owner has entered."""

    def absolute(path):
        return request.build_absolute_uri(path) if request is not None else path

    data = {
        '@context': 'https://schema.org',
        '@type': 'Restaurant',
        'name': site.name,
        'url': absolute(reverse('home')),
        'hasMenu': absolute(reverse('menu')),
        'telephone': site.phone,
        'servesCuisine': ['Iranian', 'Persian', 'Kebab'],
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': site.address,
            'addressLocality': 'Tabriz',
            'addressRegion': 'East Azerbaijan',
            'addressCountry': 'IR',
        },
    }
    if site.opens_at and site.closes_at:
        data['openingHours'] = (
            f'Mo-Su {site.opens_at:%H:%M}-{site.closes_at:%H:%M}'
        )
    if site.reservations_enabled:
        data['acceptsReservations'] = True
    if site.has_location:
        data['geo'] = {
            '@type': 'GeoCoordinates',
            'latitude': float(site.latitude),
            'longitude': float(site.longitude),
        }
    same_as = [url for url in (site.instagram_url, site.telegram_url) if url]
    if same_as:
        data['sameAs'] = same_as
    return data


@register.simple_tag(takes_context=True)
def json_ld_restaurant(context):
    """``<script type="application/ld+json">`` describing the restaurant."""
    site = context.get('site')
    if site is None:
        from saray_menu.models import SiteSettings

        site = SiteSettings.load()
    data = restaurant_json_ld(site, context.get('request'))
    payload = json.dumps(data, ensure_ascii=False, indent=None)
    # Prevent breaking out of the <script> element.
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return format_html('<script type="application/ld+json">{}</script>', mark_safe(payload))

