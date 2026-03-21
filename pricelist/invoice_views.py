"""
Invoices: list, create from proposal, detail, mark sent. Flow: proposal → invoice → order.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from .models import Invoice, Order, Proposal, get_general_settings
from .services.invoice_service import (
    allowed_invoice_status_targets,
    apply_invoice_status_change,
    create_invoice_for_proposal,
    get_invoice_for_proposal,
    proposal_allows_order_creation,
)
from .views import _get_proposal_from_identifier, _proposal_context_from_proposal


@require_http_methods(["GET"])
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
        messages.success(request, _("Draft invoice created. Review it, then mark it as sent before creating an order."))
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
def invoice_detail_view(request, pk):
    invoice = Invoice.objects.select_related(
        "proposal",
        "proposal__client_crm_organization",
        "proposal__client_crm_department",
        "proposal__client_crm_contact__person",
        "created_by",
    ).filter(uuid=pk).first()
    if invoice is None:
        raise Http404(_("No invoice found."))
    proposal = invoice.proposal
    settings = get_general_settings()
    line_data = _proposal_context_from_proposal(proposal, settings)
    order_ok, order_block_msg = proposal_allows_order_creation(proposal)
    order = Order.objects.filter(proposal_id=proposal.pk).first()
    has_order = order is not None
    status_targets = allowed_invoice_status_targets(invoice.status, has_order=has_order)
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
        },
    )


@require_POST
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
