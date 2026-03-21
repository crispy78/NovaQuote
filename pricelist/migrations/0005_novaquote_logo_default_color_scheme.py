from django.db import migrations, models


def upgrade_teal_to_novaquote_logo(apps, schema_editor):
    GeneralSettings = apps.get_model("pricelist", "GeneralSettings")
    for gs in GeneralSettings.objects.filter(color_scheme="teal"):
        gs.color_scheme = "novaquote_logo"
        gs.primary_color = "#C19A6B"
        gs.primary_color_hover = "#8B6F52"
        gs.save(update_fields=["color_scheme", "primary_color", "primary_color_hover"])


def downgrade_novaquote_logo_to_teal(apps, schema_editor):
    GeneralSettings = apps.get_model("pricelist", "GeneralSettings")
    for gs in GeneralSettings.objects.filter(color_scheme="novaquote_logo"):
        gs.color_scheme = "teal"
        gs.primary_color = "#008080"
        gs.primary_color_hover = "#006666"
        gs.save(update_fields=["color_scheme", "primary_color", "primary_color_hover"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0004_order_updated_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="generalsettings",
            name="color_scheme",
            field=models.CharField(
                choices=[
                    ("novaquote_logo", "NovaQuote logo (warm gold / brown)"),
                    ("orange", "Orange (#FFA726)"),
                    ("navy", "Navy blue (#283593)"),
                    ("teal", "Teal (#008080)"),
                    ("black", "Black (#424242)"),
                    ("red", "Red (#DC143C)"),
                ],
                default="novaquote_logo",
                help_text="Brand colour for buttons and links on the frontend and in admin.",
                max_length=32,
                verbose_name="Color scheme",
            ),
        ),
        migrations.AlterField(
            model_name="generalsettings",
            name="primary_color",
            field=models.CharField(
                default="#C19A6B",
                help_text="Synced from the selected theme for compatibility; not shown in admin.",
                max_length=9,
                verbose_name="Primary colour (legacy)",
            ),
        ),
        migrations.AlterField(
            model_name="generalsettings",
            name="primary_color_hover",
            field=models.CharField(
                blank=True,
                help_text="Optional. Darker hex for hover states. Leave empty to use an automatic darker variant of the primary colour.",
                max_length=9,
                verbose_name="Primary colour hover",
            ),
        ),
        migrations.RunPython(upgrade_teal_to_novaquote_logo, downgrade_novaquote_logo_to_teal),
    ]
