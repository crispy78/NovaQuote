"""
Invoices: list, create from proposal, detail, mark sent. Flow: proposal → invoice → order.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST
from decimal import Decimal, InvalidOperation

from .frontend_access import require_capability

from django.db.models import Prefetch

from .models import Invoice, InvoicePayment, Order, Proposal, get_general_settings
from .services.invoice_service import (
    allowed_invoice_status_targets,
    apply_invoice_status_change,
    create_invoice_for_proposal,
    delete_invoice_payment,
    get_invoice_for_proposal,
    invoice_amount_remaining,
    invoice_total_paid,
    proposal_allows_order_creation,
    record_invoice_payment,
)
from .views import _get_proposal_from_identifier, _proposal_context_from_proposal


@require_http_methods(["GET"])
@require_capability("access_invoicing")
def invoice_list_view(request):
    invoices = (
        Invoice.objects.select_related("proposal", "created_by")
        .order_by("-created_at")[:300]
    )
    settings = get_general_settings()
    return render(
        request,
        "pricelist/invoice_list.html",
        {"invoices": invoices, "settings": settings},
    )


@require_http_methods(["GET", "POST"])
@require_capability("access_invoicing")
def invoice_create_view(request, identifier):
    """Create a draft invoice from a saved proposal (GET shows confirm; POST creates)."""
    proposal = _get_proposal_from_identifier(
        identifier,
        Proposal.objects.select_related("invoice", "order"),
    )
    existing = get_invoice_for_proposal(proposal)
    if existing:
        messages.info(request, _("This proposal already has an invoice."))
        return redirect("pricelist:invoice_detail", pk=existing.uuid)

    if request.method == "POST":
        user = request.user if request.user.is_authenticated else None
        settings = get_general_settings()
        cur = (getattr(settings, "currency", None) or "EUR")[:3]
        try:
            inv = create_invoice_for_proposal(proposal, user, currency_code=cur)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("pricelist:proposal_detail", identifier=proposal.uuid)
        messages.success(
            request,
            _("Draft invoice created. Review it, then mark it as issued before creating an order."),
        )
        return redirect("pricelist:invoice_detail", pk=inv.uuid)

    settings = get_general_settings()
    data = _proposal_context_from_proposal(proposal, settings)
    return render(
        request,
        "pricelist/invoice_create_confirm.html",
        {
            "proposal": proposal,
            "grand_total": data["grand_total"],
            "settings": settings,
        },
    )


@require_http_methods(["GET"])
@require_capability("access_invoicing")
def invoice_detail_view(request, pk):
    invoice = (
        Invoice.objects.select_related(
            "proposal",
            "proposal__client_crm_organization",
            "proposal__client_crm_department",
            "proposal__client_crm_contact__person",
            "created_by",
        )
        .prefetch_related(
            Prefetch(
                "payments",
                queryset=InvoicePayment.objects.select_related("created_by").order_by(
                    "-paid_at", "-pk"
                ),
            )
        )
        .filter(uuid=pk)
        .first()
    )
    if invoice is None:
        raise Http404(_("No invoice found."))
    proposal = invoice.proposal
    settings = get_general_settings()
    line_data = _proposal_context_from_proposal(proposal, settings)
    order_ok, order_block_msg = proposal_allows_order_creation(proposal)
    order = Order.objects.filter(proposal_id=proposal.pk).first()
    has_order = order is not None
    status_targets = allowed_invoice_status_targets(invoice.status, has_order=has_order)
    total_paid = invoice_total_paid(invoice)
    remaining = invoice_amount_remaining(invoice)
    can_record_payment = invoice.status in (
        Invoice.STATUS_UNPAID,
        Invoice.STATUS_PARTIALLY_PAID,
    )
    return render(
        request,
        "pricelist/invoice_detail.html",
        {
            "invoice": invoice,
            "proposal": proposal,
            "proposal_lines": line_data["lines"],
            "grand_total": invoice.grand_total_snapshot,
            "settings": settings,
            "invoice_status_targets": status_targets,
            "can_create_order": order_ok and not has_order,
            "order_block_message": None if order_ok else order_block_msg,
            "has_order": has_order,
            "order": order,
            "invoice_total_paid": total_paid,
            "invoice_amount_remaining": remaining,
            "can_record_payment": can_record_payment,
        },
    )


@require_POST
@require_capability("access_invoicing")
def invoice_update_status_view(request, pk):
    invoice = get_object_or_404(Invoice, uuid=pk)
    new_status = (request.POST.get("status") or "").strip()
    valid = {c[0] for c in Invoice.STATUS_CHOICES}
    if new_status not in valid:
        messages.error(request, _("Invalid status."))
        return redirect("pricelist:invoice_detail", pk=invoice.uuid)
    try:
        apply_invoice_status_change(invoice, new_status)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("pricelist:invoice_detail", pk=invoice.uuid)
    messages.success(request, _("Invoice status updated."))
    return redirect("pricelist:invoice_detail", pk=invoice.uuid)


@require_POST
@require_capability("access_invoicing")
def invoice_record_payment_view(request, pk):
    invoice = get_object_or_404(Invoice, uuid=pk)
    raw = (request.POST.get("amount") or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, _("Enter a valid payment amount."))
        return redirect("pricelist:invoice_detail", pk=invoice.uuid)
    note = (request.POST.get("note") or "").strip()
    paid_at = None
    paid_raw = (request.POST.get("paid_at") or "").strip()
    if paid_raw:
        parsed = parse_datetime(paid_raw)
        if parsed is None:
            messages.error(request, _("Invalid date/time for paid at."))
            return redirect("pricelist:invoice_detail", pk=invoice.uuid)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        paid_at = parsed
    user = request.user if request.user.is_authenticated else None
    try:
        record_invoice_payment(invoice, amount, user=user, note=note, paid_at=paid_at)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("pricelist:invoice_detail", pk=invoice.uuid)
    messages.success(request, _("Payment recorded."))
    return redirect("pricelist:invoice_detail", pk=invoice.uuid)


@require_POST
@require_capability("access_invoicing")
def invoice_delete_payment_view(request, pk, payment_uuid):
    invoice = get_object_or_404(Invoice, uuid=pk)
    payment = get_object_or_404(InvoicePayment, uuid=payment_uuid, invoice_id=invoice.pk)
    delete_invoice_payment(payment)
    messages.success(request, _("Payment removed."))
    return redirect("pricelist:invoice_detail", pk=invoice.uuid)
