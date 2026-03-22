import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def default_proposal_calculation_lines_data():
    return {"version": 1, "lines": []}


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pricelist", "0006_profit_profile_sales_pricing_rules"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalCalculationModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Stable identifier for URLs and the proposal page selector.",
                        unique=True,
                        verbose_name="UUID",
                    ),
                ),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("is_active", models.BooleanField(default=True, verbose_name="Is active")),
                (
                    "lines_data",
                    models.JSONField(
                        default=default_proposal_calculation_lines_data,
                        help_text="Structured list of product/combination lines (managed via the form).",
                        verbose_name="Lines data",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proposal_calculation_models",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proposal calculation model",
                "verbose_name_plural": "Proposal calculation models",
                "db_table": "catalogus_proposalcalculationmodel",
                "ordering": ("name",),
            },
        ),
    ]
