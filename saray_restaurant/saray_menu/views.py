"""Public pages of the Saray website."""

import json
import logging
from pathlib import Path

from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist, loader
from django.urls import reverse
from django.views import defaults
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from .models import Category, MenuItem

logger = logging.getLogger(__name__)

CREDITS_PATH = Path(__file__).resolve().parent / 'data' / 'photo_credits.json'
CREDIT_FIELDS = ('key', 'title', 'author', 'license', 'license_url', 'source_url')


def _available_items():
    return MenuItem.objects.filter(is_available=True).prefetch_related('variants')


def home(request):
    featured_items = (
        _available_items()
        .filter(is_featured=True, category__is_active=True)
        .select_related('category')[:8]
    )
    # Categories with nothing available right now are left out entirely.
    categories = Category.objects.filter(is_active=True).annotate(
        item_count=Count('items', filter=Q(items__is_available=True)),
    ).filter(item_count__gt=0)
    return render(request, 'saray_menu/home.html', {
        'featured_items': featured_items,
        'categories': categories,
    })


def menu(request):
    categories = [
        category
        for category in Category.objects.filter(is_active=True).prefetch_related(
            Prefetch('items', queryset=_available_items(), to_attr='available_items'),
        )
        if category.available_items
    ]
    item_count = sum(len(category.available_items) for category in categories)
    return render(request, 'saray_menu/menu.html', {
        'categories': categories,
        'item_count': item_count,
    })


def about(request):
    return render(request, 'saray_menu/about.html')


def contact(request):
    return render(request, 'saray_menu/contact.html')


def load_photo_credits(path=None):
    """Return the photo credits as a list of dicts; a missing/invalid file yields ``[]``.

    Accepts either a bare list or ``{"credits": [...]}``.
    """
    path = Path(path) if path else CREDITS_PATH
    try:
        with open(path, encoding='utf-8') as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.warning('Could not read photo credits from %s', path, exc_info=True)
        return []
    if isinstance(raw, dict):
        raw = raw.get('credits') or raw.get('photos') or []
    if not isinstance(raw, list):
        return []
    return [
        {field: str(entry.get(field) or '') for field in CREDIT_FIELDS}
        for entry in raw
        if isinstance(entry, dict)
    ]


def credits(request):
    return render(request, 'saray_menu/credits.html', {'credits': load_photo_credits()})


@require_GET
@cache_control(max_age=60 * 60 * 24)
def robots_txt(request):
    lines = [
        'User-agent: *',
        'Disallow: /admin/',
        'Disallow: /reserve/done/',
        '',
        f'Sitemap: {request.build_absolute_uri(reverse("sitemap"))}',
        '',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')


def page_not_found(request, exception=None):
    """404 rendered with the site context (falls back to Django's default page)."""
    try:
        return render(request, '404.html', status=404)
    except TemplateDoesNotExist:
        return defaults.page_not_found(request, exception)


def server_error(request):
    """500 page: the branded template with full context if possible, otherwise the
    template without context, otherwise Django's plain page. A second failure
    (e.g. the database is down) must never hide the original error."""
    try:
        return render(request, '500.html', status=500)
    except Exception:  # noqa: BLE001 - last line of defence
        logger.exception('Branded 500 page failed to render with context')
    try:
        return HttpResponse(loader.get_template('500.html').render(), status=500)
    except Exception:  # noqa: BLE001
        logger.exception('500 template failed to render')
    return HttpResponse(PLAIN_500, status=500)


PLAIN_500 = (
    '<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>خطای سرور</title>'
    '<body style="font-family:Tahoma,sans-serif;background:#15110E;color:#F6EFE4;'
    'text-align:center;padding:4rem 1rem">'
    '<h1>متأسفیم، مشکلی پیش آمد.</h1>'
    '<p>لطفاً چند لحظهٔ دیگر دوباره تلاش کنید.</p>'
    '<p><a href="/" style="color:#E2B865">بازگشت به صفحهٔ اصلی</a></p>'
    '</body></html>'
)
