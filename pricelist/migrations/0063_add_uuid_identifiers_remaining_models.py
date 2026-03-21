import uuid

from django.db import migrations, models


def populate_missing_uuids(apps, schema_editor):
    """
    Populate remaining nullable uuid columns with uuid4 values.
    We explicitly generate values in Python to guarantee uniqueness.
    """
    model_names = [
        "GeneralSettings",
        "ProductOption",
        "PriceHistory",
        "CombinationItem",
        "ProposalHistory",
    ]
    # `apps.get_model` expects the *model class name* as defined in models.py.
    for model_name in model_names:
        Model = apps.get_model("pricelist", model_name)
        qs = Model.objects.filter(uuid__isnull=True)
        for obj in qs.iterator():
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0062_alter_order_uuid_alter_orderline_uuid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="generalsettings",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="productoption",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="pricehistory",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="combinationitem",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="proposalhistory",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),

        migrations.RunPython(populate_missing_uuids, reverse_code=migrations.RunPython.noop),

        migrations.AlterField(
            model_name="generalsettings",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="productoption",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="pricehistory",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="combinationitem",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                null=False,
                blank=False,
            ),
        ),
        migrations.AlterField(
            model_name="proposalhistory",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                null=False,
                blank=False,
            ),
        ),
    ]

