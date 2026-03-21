# CombinationItem has db_table = "catalogus_combinatieitem", so Django expects the M2M
# through table to be catalogus_combinatieitem_selected_options. Migration 0035 renamed it to
# catalogus_combinationitem_selected_options; rename back so the ORM finds it.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0037_combination_products_m2m_table_name"),
    ]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE catalogus_combinationitem_selected_options RENAME TO catalogus_combinatieitem_selected_options",
            "ALTER TABLE catalogus_combinatieitem_selected_options RENAME TO catalogus_combinationitem_selected_options",
        ),
    ]
