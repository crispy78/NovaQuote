# Rename visits_per_year to visits_per_contract (total visits in contract period).
# Migrate existing data: visits_per_contract = visits_per_year * (duration_months / 12).

from decimal import Decimal
from django.db import migrations, models


def migrate_visits_to_per_contract(apps, schema_editor):
    ContractDuration = apps.get_model("pricelist", "ContractDuration")
    for d in ContractDuration.objects.all():
        # Old: visits per year. New: total visits in contract = per_year * years
        years = float(d.duration_months) / 12
        old_per_year = float(d.visits_per_year) if hasattr(d, "visits_per_year") else 2
        d.visits_per_contract = Decimal(str(round(old_per_year * years, 2)))
        d.save(update_fields=["visits_per_contract"])


def reverse_migrate(apps, schema_editor):
    ContractDuration = apps.get_model("pricelist", "ContractDuration")
    for d in ContractDuration.objects.all():
        years = float(d.duration_months) / 12
        if years:
            d.visits_per_year = Decimal(str(round(float(d.visits_per_contract) / years, 2)))
            d.save(update_fields=["visits_per_year"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0044_show_contract_fee_calculation"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractduration",
            name="visits_per_contract",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("6.00"),
                help_text="Total number of maintenance visits in this contract period (e.g. 6 for 3 years, 10 for 5 years).",
                max_digits=6,
                verbose_name="Visits per contract period",
            ),
        ),
        migrations.RunPython(migrate_visits_to_per_contract, reverse_migrate),
        migrations.RemoveField(
            model_name="contractduration",
            name="visits_per_year",
        ),
    ]
