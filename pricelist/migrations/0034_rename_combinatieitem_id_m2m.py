# Rename combinatieitem_id to combinationitem_id in CombinationItem's M2M through table
# (geselecteerde_opties). Table catalogus_combinatieitem_geselecteerde_opties was created
# when the model was named CombinatieItem.

from django.db import migrations


def rename_column_forward(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE catalogus_combinatieitem_geselecteerde_opties "
            "RENAME COLUMN combinatieitem_id TO combinationitem_id"
        )


def rename_column_reverse(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE catalogus_combinatieitem_geselecteerde_opties "
            "RENAME COLUMN combinationitem_id TO combinatieitem_id"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0033_rename_combinatie_id_to_combination_id_m2m"),
    ]

    operations = [
        migrations.RunPython(rename_column_forward, rename_column_reverse),
    ]
