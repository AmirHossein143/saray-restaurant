"""Context shared by every public template."""

from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from .jalali import format_jalali, persian_digits, to_jalali
from .models import Category, SiteSettings


def _nav_categories():
    # Only categories that currently have something to order.
    return list(
        Category.objects.filter(is_active=True, items__is_available=True)
        .distinct()
        .only('id', 'name', 'slug', 'order')
    )


def site(request):
    """Expose ``site``, ``nav_categories``, ``current_year_fa`` and ``jalali_today``.

    Database access is lazy, so pages that never use these variables (such as
    most admin pages) do not pay for the queries.
    """
    today = timezone.localdate()
    return {
        'site': SimpleLazyObject(SiteSettings.load),
        'nav_categories': SimpleLazyObject(_nav_categories),
        'current_year_fa': persian_digits(to_jalali(today)[0]),
        'jalali_today': format_jalali(today, long=True),
    }
