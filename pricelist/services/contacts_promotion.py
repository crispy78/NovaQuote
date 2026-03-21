"""Lead → client promotion when an order is created, or when the first invoice/shipment is registered."""

from django.db import transaction
from django.utils import timezone

from ..models import Organization, OrganizationRole


def maybe_promote_lead_to_client(organization: Organization) -> None:
    """
    Promote LEAD → CLIENT: remove LEAD role, add CLIENT role, set client_since.

    Called when creating an order from a calculation (if a client/lead org is linked),
    or when the first invoice or shipment is registered for an organization.

    Skipped if auto promotion is suppressed or manual lead mode is set.
    """
    if organization.suppress_auto_client_promotion:
        return
    if organization.client_promotion_override == Organization.PROMOTION_MANUAL_LEAD:
        return
    if organization.role_assignments.filter(role=OrganizationRole.ROLE_CLIENT).exists():
        return

    with transaction.atomic():
        org = Organization.objects.select_for_update().get(pk=organization.pk)
        if org.suppress_auto_client_promotion or org.client_promotion_override == Organization.PROMOTION_MANUAL_LEAD:
            return
        if org.role_assignments.filter(role=OrganizationRole.ROLE_CLIENT).exists():
            return
        OrganizationRole.objects.filter(organization=org, role=OrganizationRole.ROLE_LEAD).delete()
        OrganizationRole.objects.get_or_create(organization=org, role=OrganizationRole.ROLE_CLIENT)
        now = timezone.now()
        if org.client_since is None:
            org.client_since = now
            org.save(update_fields=["client_since"])
