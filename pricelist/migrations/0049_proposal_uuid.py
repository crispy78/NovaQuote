# Proposal gets a stable UUID for URLs; reachable via /proposal/saved/<uuid>/ or by reference.

import uuid

from django.db import migrations, models


def fill_proposal_uuids(apps, schema_editor):
    Proposal = apps.get_model("pricelist", "Proposal")
    for obj in Proposal.objects.all():
        if not obj.uuid:
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0048_contract_duration_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposal",
            name="uuid",
            field=models.UUIDField(
                editable=False,
                null=True,
                verbose_name="UUID",
                help_text="Stable identifier for URLs; proposal is reachable via /proposal/saved/<uuid>/ or by reference.",
            ),
        ),
        migrations.RunPython(fill_proposal_uuids, noop),
        migrations.AlterField(
            model_name="proposal",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="UUID",
                help_text="Stable identifier for URLs; proposal is reachable via /proposal/saved/<uuid>/ or by reference.",
            ),
        ),
    ]
