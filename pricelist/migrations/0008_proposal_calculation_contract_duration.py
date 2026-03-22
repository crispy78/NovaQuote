import django.db.models.deletion
from django.db import migrations, models


def default_contract_calculation_options():
    return {
        "version": 1,
        "hardware_fee_basis": "sales_line_totals",
        "labour_unit_basis": "all_units",
        "include_hardware_fee": True,
        "include_labour": True,
        "override_time_per_product_minutes": None,
        "override_minimum_visit_minutes": None,
        "override_hourly_rate": None,
        "override_hardware_fee_percentage": None,
        "override_visits_per_contract": None,
    }


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0007_proposal_calculation_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalcalculationmodel",
            name="contract_calculation_options",
            field=models.JSONField(
                default=default_contract_calculation_options,
                help_text="What counts toward hardware fee and labour; optional overrides (managed via the form).",
                verbose_name="Contract calculation options",
            ),
        ),
        migrations.AddField(
            model_name="proposalcalculationmodel",
            name="contract_duration",
            field=models.ForeignKey(
                blank=True,
                help_text="Maintenance contract period this model belongs to. On the proposal, only this contract block is shown when the model is applied.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="proposal_calculation_models",
                to="pricelist.contractduration",
                verbose_name="Contract duration",
            ),
        ),
    ]
