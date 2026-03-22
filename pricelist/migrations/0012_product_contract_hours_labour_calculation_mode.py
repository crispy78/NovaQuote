# Generated manually for NovaQuote contract hours feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0011_contract_duration_calculation_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractduration",
            name="labour_calculation_mode",
            field=models.CharField(
                choices=[
                    (
                        "visit_time",
                        "Visit time (minutes × units, minimum visit, × visits per contract)",
                    ),
                    (
                        "contract_hours",
                        "Product contract hours (hours/year from catalog × quantity × hourly rate)",
                    ),
                ],
                default="visit_time",
                help_text="Visit time uses minutes per product and visits. Contract hours uses each product’s contract hours (and period) from the catalog, scaled to the contract length.",
                max_length=32,
                verbose_name="Labour calculation",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="contract_hours",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional. Maintenance hours covered for this product (see period). Used when a contract duration uses labour from product contract hours.",
                max_digits=8,
                null=True,
                verbose_name="Contract hours",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="contract_hours_period",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "— Not set —"),
                    ("week", "Per week"),
                    ("month", "Per month"),
                    ("quarter", "Per quarter"),
                    ("year", "Per year"),
                ],
                help_text="How often the contract hours amount applies (e.g. hours per month).",
                max_length=16,
                verbose_name="Contract hours period",
            ),
        ),
    ]
