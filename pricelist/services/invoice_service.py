"""
Invoice creation and lifecycle (proposal → invoice → order).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from pricelist.models import Invoice, Order, Proposal


def get_invoice_for_proposal(proposal: Proposal) -> Invoice | None:
    return Invoice.objects.filter(proposal_id=proposal.pk).first()


@transaction.atomic
def create_invoice_for_proposal(proposal: Proposal, user, currency_code: str = "EUR") -> Invoice:
    """Create a draft invoice with amounts frozen from the current proposal lines."""
    if get_invoice_for_proposal(proposal) is not None:
        raise ValueError(_("This proposal already has an invoice."))
    total = proposal.grand_total_snapshot()
    if total is None:
        total = Decimal("0.00")
    return Invoice.objects.create(
        proposal=proposal,
        status=Invoice.STATUS_DRAFT,
        grand_total_snapshot=total,
        currency_code=(currency_code or "EUR")[:3],
        created_by=user,
    )


@transaction.atomic
def mark_invoice_sent(invoice: Invoice) -> None:
    """Issue (or re-issue) the invoice to the customer; promotes CRM lead→client when applicable."""
    invoice.status = Invoice.STATUS_SENT
    invoice.issued_at = timezone.now()
    if not (invoice.invoice_number or "").strip():
        invoice.invoice_number = f"INV-{timezone.now().year}-{invoice.pk:05d}"
    invoice.save(update_fields=["status", "issued_at", "invoice_number", "updated_at"])

    proposal = invoice.proposal
    if proposal.client_crm_organization_id:
        from .contacts_promotion import maybe_promote_lead_to_client

        maybe_promote_lead_to_client(proposal.client_crm_organization)


def allowed_invoice_status_targets(current: str, *, has_order: bool) -> list[tuple[str, str]]:
    """Return (value, label) pairs for statuses the user may switch to from the current one."""
    labels = dict(Invoice.STATUS_CHOICES)
    out: list[tuple[str, str]] = []
    if current == Invoice.STATUS_DRAFT:
        out = [
            (Invoice.STATUS_SENT, labels[Invoice.STATUS_SENT]),
            (Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]),
        ]
    elif current == Invoice.STATUS_SENT:
        if not has_order:
            out.append((Invoice.STATUS_DRAFT, labels[Invoice.STATUS_DRAFT]))
        out.extend(
            [
                (Invoice.STATUS_PAID, labels[Invoice.STATUS_PAID]),
                (Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]),
            ]
        )
    elif current == Invoice.STATUS_PAID:
        out = [
            (Invoice.STATUS_SENT, labels[Invoice.STATUS_SENT]),
            (Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]),
        ]
    elif current == Invoice.STATUS_CANCELLED:
        out = [
            (Invoice.STATUS_DRAFT, labels[Invoice.STATUS_DRAFT]),
            (Invoice.STATUS_SENT, labels[Invoice.STATUS_SENT]),
        ]
    return out


@transaction.atomic
def apply_invoice_status_change(invoice: Invoice, new_status: str) -> None:
    """
    Apply a user-selected status change with basic business rules.
    """
    invoice.refresh_from_db()
    old = invoice.status
    if old == new_status:
        return
    has_order = Order.objects.filter(proposal_id=invoice.proposal_id).exists()
    permitted = {t[0] for t in allowed_invoice_status_targets(old, has_order=has_order)}
    if new_status not in permitted:
        raise ValueError(_("This status change is not allowed."))

    if new_status == Invoice.STATUS_DRAFT:
        if has_order:
            raise ValueError(
                _("You cannot set this invoice to draft while a purchase order exists for this calculation.")
            )
        if old not in (Invoice.STATUS_SENT, Invoice.STATUS_PAID, Invoice.STATUS_CANCELLED):
            raise ValueError(_("Invalid status change."))
        invoice.status = Invoice.STATUS_DRAFT
        invoice.issued_at = None
        invoice.save(update_fields=["status", "issued_at", "updated_at"])
        return

    if new_status == Invoice.STATUS_SENT:
        if old in (Invoice.STATUS_DRAFT, Invoice.STATUS_CANCELLED):
            mark_invoice_sent(invoice)
            return
        if old == Invoice.STATUS_PAID:
            invoice.status = Invoice.STATUS_SENT
            invoice.save(update_fields=["status", "updated_at"])
            return
        raise ValueError(_("Invalid status change."))

    if new_status == Invoice.STATUS_PAID:
        if old != Invoice.STATUS_SENT:
            raise ValueError(_("Only a sent invoice can be marked as paid."))
        invoice.status = Invoice.STATUS_PAID
        invoice.save(update_fields=["status", "updated_at"])
        return

    if new_status == Invoice.STATUS_CANCELLED:
        if old not in (Invoice.STATUS_DRAFT, Invoice.STATUS_SENT, Invoice.STATUS_PAID):
            raise ValueError(_("Invalid status change."))
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
        return

    raise ValueError(_("Unknown status."))


def proposal_allows_order_creation(proposal: Proposal) -> tuple[bool, str | None]:
    """
    Orders require a sent (or paid) invoice first.
    Returns (allowed, error_message_for_user).
    """
    inv = get_invoice_for_proposal(proposal)
    if inv is None:
        return False, _("Create an invoice for this proposal first, then mark it as sent before placing an order.")
    if inv.status not in (Invoice.STATUS_SENT, Invoice.STATUS_PAID):
        return False, _("Mark the invoice as sent before creating an order. This records the amount owed before purchasing.")
    return True, None
