# ContractDuration gets a stable UUID; ProposalContractSnapshot stores it for matching by UUID.

import uuid

from django.db import migrations, models


def fill_contract_duration_uuids(apps, schema_editor):
    ContractDuration = apps.get_model("pricelist", "ContractDuration")
    for obj in ContractDuration.objects.all():
        if not obj.uuid:
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=["uuid"])


def fill_snapshot_uuids(apps, schema_editor):
    ProposalContractSnapshot = apps.get_model("pricelist", "ProposalContractSnapshot")
    for snap in ProposalContractSnapshot.objects.select_related("contract_duration").all():
        if snap.contract_duration_id and snap.contract_duration.uuid and not snap.contract_duration_uuid:
            snap.contract_duration_uuid = snap.contract_duration.uuid
            snap.save(update_fields=["contract_duration_uuid"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0047_proposal_contract_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractduration",
            name="uuid",
            field=models.UUIDField(
                editable=False,
                null=True,
                verbose_name="UUID",
                help_text="Stable identifier so snapshots stay linked to this contract form even if name is reused.",
            ),
        ),
        migrations.AddField(
            model_name="proposalcontractsnapshot",
            name="contract_duration_uuid",
            field=models.UUIDField(
                blank=True,
                null=True,
                verbose_name="Contract duration UUID",
                help_text="UUID of the contract form at save time; used to match even if a new form has the same name.",
            ),
        ),
        migrations.RunPython(fill_contract_duration_uuids, noop),
        migrations.RunPython(fill_snapshot_uuids, noop),
        migrations.AlterField(
            model_name="contractduration",
            name="uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="UUID",
                help_text="Stable identifier so snapshots stay linked to this contract form even if name is reused.",
            ),
        ),
    ]
