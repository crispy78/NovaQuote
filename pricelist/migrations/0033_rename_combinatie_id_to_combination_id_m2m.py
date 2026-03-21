# Rename combinatie_id to combination_id in M2M table so it matches the Combination model name.
# The table catalogus_combinatie_producten was created when the model was named Combinatie.

from django.db import migrations


def rename_column_forward(apps, schema_editor):
    # SQLite 3.35+ and PostgreSQL support RENAME COLUMN
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE catalogus_combinatie_producten RENAME COLUMN combinatie_id TO combination_id"
        )


def rename_column_reverse(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE catalogus_combinatie_producten RENAME COLUMN combination_id TO combinatie_id"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0032_rename_product_afbeeldingen_to_product_images"),
    ]

    operations = [
        migrations.RunPython(rename_column_forward, rename_column_reverse),
    ]
