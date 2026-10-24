"""Load the real menu (data/menu_seed.json) and the SiteSettings row."""

from django.db import migrations

from saray_menu.migrations._seed_v1 import ensure_site_settings, import_menu_data, load_seed


def seed(apps, schema_editor):
    ensure_site_settings(apps.get_model('saray_menu', 'SiteSettings'))
    import_menu_data(
        load_seed(),
        apps.get_model('saray_menu', 'Category'),
        apps.get_model('saray_menu', 'MenuItem'),
        apps.get_model('saray_menu', 'MenuItemVariant'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('saray_menu', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
