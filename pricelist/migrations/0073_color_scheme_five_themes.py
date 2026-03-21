# Map legacy color_scheme values to the five fixed themes; sync primary/hover hex.

from django.db import migrations, models

OLD_TO_NEW = {
    "house_orange": "orange",
    "summer": "orange",
    "autumn": "orange",
    "teal": "teal",
    "spring": "teal",
    "winter": "teal",
    "graytone": "black",
    "high_contrast": "navy",
    "custom": "teal",
}

PALETTES = {
    "orange": ("#FFA726", "#F57C00"),
    "navy": ("#283593", "#1A237E"),
    "teal": ("#008080", "#006666"),
    "black": ("#424242", "#212121"),
    "red": ("#DC143C", "#AD102F"),
}


def forwards(apps, schema_editor):
    GeneralSettings = apps.get_model("pricelist", "GeneralSettings")
    for row in GeneralSettings.objects.all():
        key = OLD_TO_NEW.get(row.color_scheme, row.color_scheme)
        if key not in PALETTES:
            key = "teal"
        row.color_scheme = key
        row.primary_color, row.primary_color_hover = PALETTES[key]
        row.save(update_fields=["color_scheme", "primary_color", "primary_color_hover"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0072_generalsettings_color_scheme"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="generalsettings",
            name="color_scheme",
            field=models.CharField(
                choices=[
                    ("orange", "Orange (#FFA726)"),
                    ("navy", "Navy blue (#283593)"),
                    ("teal", "Teal (#008080)"),
                    ("black", "Black (#424242)"),
                    ("red", "Red (#DC143C)"),
                ],
                default="teal",
                help_text="Brand colour for buttons and links on the frontend and in admin.",
                max_length=32,
                verbose_name="Color scheme",
            ),
        ),
        migrations.AlterField(
            model_name="generalsettings",
            name="primary_color",
            field=models.CharField(
                default="#008080",
                help_text="Synced from the selected theme for compatibility; not shown in admin.",
                max_length=9,
                verbose_name="Primary colour (legacy)",
            ),
        ),
    ]
