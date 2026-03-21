import uuid

from django.db import migrations, models


def populate_missing_uuids(apps, schema_editor):
    """
    Populate uuid fields that were added as nullable during migration.
    We generate fresh uuid4 values per row to guarantee uniqueness.
    """
    model_names = [
        "ProposalLine",
        "ProposalLineOption",
        "ProposalContractSnapshot",
        "Order",
        "OrderLine",
        "OrderLineItem",
    ]
    for model_name in model_names:
        Model = apps.get_model("pricelist", model_name)
        # uuid field exists at this point (added earlier in this migration)
        qs = Model.objects.filter(uuid__isnull=True)
        for obj in qs.iterator():
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0060_alter_product_table"),
    ]

    operations = [
        # 1) Add UUID fields as nullable + non-unique to avoid callable-unique pitfalls.
        migrations.AddField(
            model_name="proposalline",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="proposallineoption",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="proposalcontractsnapshot",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="order",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="orderline",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        migrations.AddField(
            model_name="orderlineitem",
            name="uuid",
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),

        # 2) Populate missing UUIDs with uuid4.
        migrations.RunPython(populate_missing_uuids, reverse_code=migrations.RunPython.noop),

        # 3) Enforce uniqueness + non-null and keep default for future rows.
        migrations.AlterField(
            model_name="proposalline",
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
            model_name="proposallineoption",
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
            model_name="proposalcontractsnapshot",
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
            model_name="order",
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
            model_name="orderline",
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
            model_name="orderlineitem",
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

