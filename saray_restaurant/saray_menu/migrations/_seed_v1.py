"""Frozen copy of the menu importer used by migration 0002.

Data migrations must not depend on code that keeps evolving (saray_menu.seed
may later set fields that don't exist at this point in the migration
history). Modules whose names start with "_" are ignored by Django's
migration loader.
"""

import json
from dataclasses import dataclass
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parent.parent / 'data' / 'menu_seed.json'


@dataclass
class ImportResult:
    categories_created: int = 0
    categories_updated: int = 0
    items_created: int = 0
    items_updated: int = 0
    variants_created: int = 0
    variants_updated: int = 0


def load_seed(path=None):
    with open(path or SEED_PATH, encoding='utf-8') as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get('categories'), list):
        raise ValueError('Menu file must be an object with a "categories" list.')
    return data


def import_menu_data(data, Category, MenuItem, MenuItemVariant):
    """Create or update categories/items/variants from parsed seed ``data``.

    Model classes are passed in so the function works with historical models
    inside migrations.
    """
    result = ImportResult()
    for c_order, cat in enumerate(data['categories'], start=1):
        category, created = Category.objects.update_or_create(
            slug=cat['slug'],
            defaults={
                'name': cat['name'],
                'name_en': cat.get('name_en') or '',
                'description': cat.get('description') or '',
                'icon': cat.get('icon') or 'skewer',
                'stock_photo': cat.get('photo') or '',
                'order': c_order * 10,
            },
        )
        if created:
            result.categories_created += 1
        else:
            result.categories_updated += 1

        for i_order, entry in enumerate(cat.get('items', []), start=1):
            item, created = MenuItem.objects.update_or_create(
                slug=entry['slug'],
                defaults={
                    'category': category,
                    'name': entry['name'],
                    'name_en': entry.get('name_en') or '',
                    'description': entry.get('description') or '',
                    'price': entry.get('price'),
                    'stock_photo': entry.get('photo') or '',
                    'is_featured': bool(entry.get('is_featured')),
                    'is_spicy': bool(entry.get('is_spicy')),
                    'is_vegetarian': bool(entry.get('is_vegetarian')),
                    'order': i_order * 10,
                },
            )
            if created:
                result.items_created += 1
            else:
                result.items_updated += 1

            for v_order, variant in enumerate(entry.get('variants') or [], start=1):
                _, created = MenuItemVariant.objects.update_or_create(
                    item=item,
                    label=variant['label'],
                    defaults={'price': variant['price'], 'order': v_order * 10},
                )
                if created:
                    result.variants_created += 1
                else:
                    result.variants_updated += 1
    return result


def ensure_site_settings(SiteSettings):
    """Create the singleton settings row (field defaults hold the real content)."""
    obj, _ = SiteSettings.objects.get_or_create(pk=1)
    return obj
