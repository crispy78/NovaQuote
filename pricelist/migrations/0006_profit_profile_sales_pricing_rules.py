import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0005_novaquote_logo_default_color_scheme"),
    ]

    operations = [
        migrations.AddField(
            model_name="profitprofile",
            name="use_sales_pricing_rules",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, sales price follows the ordered rule rows below (first match wins; optional catch-all row). "
                    "When disabled, the flat markup fields are used."
                ),
                verbose_name="Use decision table for sales price",
            ),
        ),
        migrations.CreateModel(
            name="SalesPricingRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID")),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Lower numbers are evaluated first.",
                        verbose_name="Order",
                    ),
                ),
                (
                    "is_fallback",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "If checked, this row applies when no other row matches. Leave the condition empty for this row."
                        ),
                        verbose_name="Else (catch-all)",
                    ),
                ),
                (
                    "condition_operator",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("lt", "is less than"),
                            ("lte", "is less than or equal to"),
                            ("gt", "is greater than"),
                            ("gte", "is greater than or equal to"),
                            ("eq", "equals"),
                            ("between", "is between"),
                        ],
                        help_text="Compared to catalog cost price. Not used for a catch-all row.",
                        max_length=16,
                        verbose_name="Cost price",
                    ),
                ),
                (
                    "condition_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text='Compare cost to this amount (lower bound for "between").',
                        max_digits=12,
                        null=True,
                        verbose_name="Value",
                    ),
                ),
                (
                    "condition_value_to",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text='Upper bound when using "between" (inclusive).',
                        max_digits=12,
                        null=True,
                        verbose_name="Upper value",
                    ),
                ),
                (
                    "markup_percentage",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Percentage on cost (e.g. 20 for 20%).",
                        max_digits=5,
                        verbose_name="Markup %",
                    ),
                ),
                (
                    "markup_fixed",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Added after percentage markup.",
                        max_digits=10,
                        verbose_name="Fixed markup",
                    ),
                ),
                (
                    "profit_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sales_pricing_rules",
                        to="pricelist.profitprofile",
                        verbose_name="Profit profile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sales pricing rule",
                "verbose_name_plural": "Sales pricing rules",
                "db_table": "catalogus_salespricingrule",
                "ordering": ("profit_profile", "sort_order", "id"),
            },
        ),
    ]
