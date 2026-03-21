# Combination has db_table = "catalogus_combinatie", so Django expects the M2M
# through table to be catalogus_combinatie_products. Migration 0035 renamed it to
# catalogus_combination_products; rename back so the ORM finds it.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0036_rename_combinatie_combination_state_only"),
    ]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE catalogus_combination_products RENAME TO catalogus_combinatie_products",
            "ALTER TABLE catalogus_combinatie_products RENAME TO catalogus_combination_products",
        ),
    ]
