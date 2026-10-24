"""``python manage.py import_menu [--file path.json]`` — (re)load the menu seed."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from saray_menu.seed import SEED_PATH, import_menu


class Command(BaseCommand):
    help = (
        'Create or update menu categories, items and variants from a JSON seed file '
        '(matched by slug, so running it again is safe). Note: prices and texts in '
        'the database are overwritten with the values from the file.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', dest='path', default=str(SEED_PATH),
            help=f'Path to the menu JSON file (default: {SEED_PATH}).',
        )

    def handle(self, *args, path, **options):
        try:
            with transaction.atomic():
                result = import_menu(path)
        except FileNotFoundError as exc:
            raise CommandError(f'File not found: {path}') from exc
        except (ValueError, KeyError) as exc:
            raise CommandError(f'Invalid menu file: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(
            'Menu imported: '
            f'categories +{result.categories_created} ~{result.categories_updated}, '
            f'items +{result.items_created} ~{result.items_updated}, '
            f'variants +{result.variants_created} ~{result.variants_updated}.'
        ))
