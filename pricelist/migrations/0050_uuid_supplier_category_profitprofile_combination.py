# Add UUID to Supplier, Category, ProfitProfile, Combination (stable identifiers, not dependent on DB location).

import uuid

from django.db import migrations, models


def fill_supplier_uuids(apps, schema_editor):
    for obj in apps.get_model("pricelist", "Supplier").objects.all():
        if not getattr(obj, "uuid", None):
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def fill_category_uuids(apps, schema_editor):
    for obj in apps.get_model("pricelist", "Category").objects.all():
        if not getattr(obj, "uuid", None):
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def fill_profitprofile_uuids(apps, schema_editor):
    for obj in apps.get_model("pricelist", "ProfitProfile").objects.all():
        if not getattr(obj, "uuid", None):
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def fill_combination_uuids(apps, schema_editor):
    for obj in apps.get_model("pricelist", "Combination").objects.all():
        if not getattr(obj, "uuid", None):
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0049_proposal_uuid"),
    ]

    operations = [
        # Supplier
        migrations.AddField(
            model_name="supplier",
            name="uuid",
            field=models.UUIDField(editable=False, null=True, unique=False, verbose_name="UUID"),
        ),
        migrations.RunPython(fill_supplier_uuids, noop),
        migrations.AlterField(
            model_name="supplier",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID"),
        ),
        # Category
        migrations.AddField(
            model_name="category",
            name="uuid",
            field=models.UUIDField(editable=False, null=True, unique=False, verbose_name="UUID"),
        ),
        migrations.RunPython(fill_category_uuids, noop),
        migrations.AlterField(
            model_name="category",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID"),
        ),
        # ProfitProfile
        migrations.AddField(
            model_name="profitprofile",
            name="uuid",
            field=models.UUIDField(editable=False, null=True, unique=False, verbose_name="UUID"),
        ),
        migrations.RunPython(fill_profitprofile_uuids, noop),
        migrations.AlterField(
            model_name="profitprofile",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID"),
        ),
        # Combination
        migrations.AddField(
            model_name="combination",
            name="uuid",
            field=models.UUIDField(editable=False, null=True, unique=False, verbose_name="UUID"),
        ),
        migrations.RunPython(fill_combination_uuids, noop),
        migrations.AlterField(
            model_name="combination",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="UUID"),
        ),
    ]
