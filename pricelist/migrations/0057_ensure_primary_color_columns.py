# Migration to add primary_color and primary_color_hover columns if missing
# (fixes OperationalError when DB was out of sync with migration 0056)

from django.db import migrations


def ensure_columns(apps, schema_editor):
    """Add primary_color and primary_color_hover to catalogus_generalsettings if they don't exist."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(catalogus_generalsettings)")
        columns = [row[1] for row in cursor.fetchall()]
    if "primary_color" not in columns:
        schema_editor.execute(
            "ALTER TABLE catalogus_generalsettings ADD COLUMN primary_color VARCHAR(9) NOT NULL DEFAULT '#e01581'"
        )
    if "primary_color_hover" not in columns:
        schema_editor.execute(
            "ALTER TABLE catalogus_generalsettings ADD COLUMN primary_color_hover VARCHAR(9) NOT NULL DEFAULT ''"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0056_general_settings_primary_color"),
    ]

    operations = [
        migrations.RunPython(ensure_columns, noop_reverse),
    ]
