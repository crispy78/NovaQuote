"""
Invoice creation and lifecycle (proposal → invoice → order).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from pricelist.models import Invoice, InvoicePayment, Order, Proposal


def get_invoice_for_proposal(proposal: Proposal) -> Invoice | None:
    return Invoice.objects.filter(proposal_id=proposal.pk).first()


def invoice_total_paid(invoice: Invoice) -> Decimal:
    total = invoice.payments.aggregate(s=Sum("amount"))["s"]
    return total if total is not None else Decimal("0.00")


def invoice_amount_remaining(invoice: Invoice) -> Decimal:
    grand = invoice.grand_total_snapshot or Decimal("0.00")
    return grand - invoice_total_paid(invoice)


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
    """Issue the invoice to the customer (unpaid until payments are recorded). Promotes CRM lead→client when applicable."""
    invoice.status = Invoice.STATUS_UNPAID
    invoice.issued_at = timezone.now()
    if not (invoice.invoice_number or "").strip():
        invoice.invoice_number = f"INV-{timezone.now().year}-{invoice.pk:05d}"
    invoice.save(update_fields=["status", "issued_at", "invoice_number", "updated_at"])

    proposal = invoice.proposal
    if proposal.client_crm_organization_id:
        from .contacts_promotion import maybe_promote_lead_to_client

        maybe_promote_lead_to_client(proposal.client_crm_organization)


@transaction.atomic
def sync_invoice_status_from_payments(invoice: Invoice) -> None:
    """
    Set invoice to unpaid / partially_paid / paid from recorded payments.
    Does not change draft or cancelled.
    """
    invoice.refresh_from_db()
    if invoice.status in (Invoice.STATUS_DRAFT, Invoice.STATUS_CANCELLED):
        return
    total_paid = invoice_total_paid(invoice)
    grand = invoice.grand_total_snapshot or Decimal("0.00")
    old_status = invoice.status
    if total_paid <= 0:
        new_status = Invoice.STATUS_UNPAID
    elif total_paid < grand:
        new_status = Invoice.STATUS_PARTIALLY_PAID
    else:
        new_status = Invoice.STATUS_PAID
    if invoice.status != new_status:
        invoice.status = new_status
        invoice.save(update_fields=["status", "updated_at"])
    if new_status == Invoice.STATUS_PAID and old_status != Invoice.STATUS_PAID:
        sync_order_paid_for_invoice(invoice)


@transaction.atomic
def sync_order_paid_for_invoice(invoice: Invoice) -> None:
    """When the customer invoice is fully paid, mark linked purchase order as paid if still draft or sent."""
    order = Order.objects.filter(proposal_id=invoice.proposal_id).first()
    if not order:
        return
    if order.status == Order.STATUS_CANCELLED:
        return
    if order.status in (Order.STATUS_DRAFT, Order.STATUS_SENT):
        order.status = Order.STATUS_PAID
        order.save(update_fields=["status", "updated_at"])


@transaction.atomic
def record_invoice_payment(
    invoice: Invoice,
    amount: Decimal,
    *,
    user,
    note: str = "",
    paid_at=None,
) -> InvoicePayment:
    """Record a partial or full payment. Updates invoice status and may set the order to paid."""
    if invoice.status == Invoice.STATUS_DRAFT:
        raise ValueError(_("Record payments only after the invoice is issued."))
    if invoice.status == Invoice.STATUS_CANCELLED:
        raise ValueError(_("Cannot record payments on a cancelled invoice."))
    if amount <= 0:
        raise ValueError(_("Payment amount must be greater than zero."))
    remaining = invoice_amount_remaining(invoice)
    if amount > remaining:
        raise ValueError(
            _("Payment exceeds the remaining balance (%(remaining)s).")
            % {"remaining": remaining}
        )
    when = paid_at if paid_at is not None else timezone.now()
    payment = InvoicePayment.objects.create(
        invoice=invoice,
        amount=amount,
        paid_at=when,
        note=(note or "").strip(),
        created_by=user,
    )
    sync_invoice_status_from_payments(invoice)
    return payment


@transaction.atomic
def delete_invoice_payment(payment: InvoicePayment) -> None:
    """Remove a payment row and recalculate invoice (and order) status."""
    invoice_id = payment.invoice_id
    payment.delete()
    invoice = Invoice.objects.get(pk=invoice_id)
    sync_invoice_status_from_payments(invoice)
    invoice.refresh_from_db()
    # If no longer fully paid, reopen order from paid → sent when it was auto-set
    order = Order.objects.filter(proposal_id=invoice.proposal_id).first()
    if (
        order
        and order.status == Order.STATUS_PAID
        and invoice.status not in (Invoice.STATUS_PAID, Invoice.STATUS_CANCELLED)
    ):
        order.status = Order.STATUS_SENT
        order.save(update_fields=["status", "updated_at"])


def allowed_invoice_status_targets(current: str, *, has_order: bool) -> list[tuple[str, str]]:
    """Return (value, label) pairs for statuses the user may switch to from the current one."""
    labels = dict(Invoice.STATUS_CHOICES)
    out: list[tuple[str, str]] = []
    if current == Invoice.STATUS_DRAFT:
        out = [
            (Invoice.STATUS_UNPAID, _("Mark as issued")),
            (Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]),
        ]
    elif current == Invoice.STATUS_UNPAID:
        if not has_order:
            out.append((Invoice.STATUS_DRAFT, labels[Invoice.STATUS_DRAFT]))
        out.append((Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]))
    elif current == Invoice.STATUS_PARTIALLY_PAID:
        if not has_order:
            out.append((Invoice.STATUS_DRAFT, labels[Invoice.STATUS_DRAFT]))
        out.append((Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED]))
    elif current == Invoice.STATUS_PAID:
        out = [(Invoice.STATUS_CANCELLED, labels[Invoice.STATUS_CANCELLED])]
    elif current == Invoice.STATUS_CANCELLED:
        out = [
            (Invoice.STATUS_DRAFT, labels[Invoice.STATUS_DRAFT]),
            (Invoice.STATUS_UNPAID, _("Mark as issued")),
        ]
    return out


@transaction.atomic
def apply_invoice_status_change(invoice: Invoice, new_status: str) -> None:
    """
    Apply a user-selected status change with basic business rules.
    Payment-driven statuses (unpaid, partially_paid, paid) are updated when payments are added or removed.
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
        if invoice.payments.exists():
            raise ValueError(_("Remove all payments before setting the invoice to draft."))
        if old not in (
            Invoice.STATUS_UNPAID,
            Invoice.STATUS_PARTIALLY_PAID,
            Invoice.STATUS_CANCELLED,
        ):
            raise ValueError(_("Invalid status change."))
        invoice.status = Invoice.STATUS_DRAFT
        invoice.issued_at = None
        invoice.save(update_fields=["status", "issued_at", "updated_at"])
        return

    if new_status == Invoice.STATUS_UNPAID:
        if old in (Invoice.STATUS_DRAFT, Invoice.STATUS_CANCELLED):
            mark_invoice_sent(invoice)
            return
        raise ValueError(_("Invalid status change."))

    if new_status == Invoice.STATUS_CANCELLED:
        if old not in (
            Invoice.STATUS_DRAFT,
            Invoice.STATUS_UNPAID,
            Invoice.STATUS_PARTIALLY_PAID,
            Invoice.STATUS_PAID,
        ):
            raise ValueError(_("Invalid status change."))
        invoice.status = Invoice.STATUS_CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
        return

    raise ValueError(_("Unknown status."))


def proposal_allows_order_creation(proposal: Proposal) -> tuple[bool, str | None]:
    """
    Orders require an issued invoice first (unpaid, partially paid, or paid).
    """
    inv = get_invoice_for_proposal(proposal)
    if inv is None:
        return False, _("Create an invoice for this proposal first, then mark it as issued before placing an order.")
    if inv.status not in (
        Invoice.STATUS_UNPAID,
        Invoice.STATUS_PARTIALLY_PAID,
        Invoice.STATUS_PAID,
    ):
        return False, _("Mark the invoice as issued before creating an order. This records the amount owed before purchasing.")
    return True, None
