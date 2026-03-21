# Soft delete for catalog Product and Combination

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0073_color_scheme_five_themes"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When set, this product is hidden from the catalog. Staff can restore or purge.",
                null=True,
                verbose_name="Removed at",
            ),
        ),
        migrations.AddField(
            model_name="combination",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When set, this combination is hidden from the catalog. Staff can restore or purge.",
                null=True,
                verbose_name="Removed at",
            ),
        ),
    ]
