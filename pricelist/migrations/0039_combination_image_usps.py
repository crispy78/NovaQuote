# Add image and usps to Combination. Table name is catalogus_combinatie (db_table).

import pricelist.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricelist', '0038_combinationitem_selected_options_m2m_table_name'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='combination',
                    name='image',
                    field=models.ImageField(blank=True, null=True, upload_to=pricelist.models.combination_image_upload_to, verbose_name='Image'),
                ),
                migrations.AddField(
                    model_name='combination',
                    name='usps',
                    field=models.TextField(blank=True, help_text='USPs, one per line.', verbose_name='USPs'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE catalogus_combinatie ADD COLUMN image VARCHAR(100)",
                    "ALTER TABLE catalogus_combinatie DROP COLUMN image",
                ),
                migrations.RunSQL(
                    "ALTER TABLE catalogus_combinatie ADD COLUMN usps TEXT DEFAULT '' NOT NULL",
                    "ALTER TABLE catalogus_combinatie DROP COLUMN usps",
                ),
            ],
        ),
    ]
