"""
Order domain/service functions.

Goal: keep Django views thin by moving order creation, supplier grouping and POST persistence
into a dedicated service module.
"""

from __future__ import annotations

import uuid as uuid_lib
from collections import OrderedDict
from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _

from pricelist.models import (
    Department,
    Invoice,
    Order,
    OrderLine,
    OrderLineItem,
    OrganizationPerson,
    ProposalLine,
)


def create_order_from_proposal(proposal, user, invoice: Invoice | None = None) -> Order:
    """
    Create an `Order` (and its `OrderLine` + `OrderLineItem` rows) from a saved `Proposal`.

    - One `OrderLine` per proposal line.
    - For a product proposal line: one `OrderLineItem` (combination_item=None).
    - For a combination proposal line: one `OrderLineItem` per `CombinationItem`.
    """
    if hasattr(proposal, "order"):
        # If the order already exists we reuse it; callers can decide what to do.
        return proposal.order

    if invoice is None:
        invoice = Invoice.objects.filter(proposal_id=proposal.pk).first()
    order = Order.objects.create(
        proposal=proposal,
        reference=proposal.reference or "",
        created_by=user,
        invoice=invoice,
    )

    proposal_lines = (
        proposal.lines.select_related("product", "combination", "product_supplier", "product_supplier__supplier")
        .prefetch_related("combination__items")
        .order_by("sort_order", "id")
    )

    for pl in proposal_lines:
        ol = OrderLine.objects.create(order=order, proposal_line=pl)
        if (
            pl.line_type == ProposalLine.LINE_TYPE_COMBINATION
            and pl.combination_id
            and pl.combination
        ):
            for item in pl.combination.items.all():
                OrderLineItem.objects.create(order_line=ol, combination_item=item)
        else:
            OrderLineItem.objects.create(order_line=ol, combination_item=None)

    # Lead → client promotion runs when the invoice is marked sent (see invoice_service), not here.

    return order


def build_supplier_groups(order: Order) -> List[Dict[str, Any]]:
    """
    Build per-supplier rows for the order detail table.

    Each displayed row is one `OrderLineItem` so the user can update
    ordered_at/expected_delivery/delivered_at per item.
    """
    order_line_items = (
        OrderLineItem.objects.filter(order_line__order=order)
        .select_related(
            "order_line",
            "order_line__proposal_line",
            "order_line__proposal_line__product",
            "order_line__proposal_line__product__supplier",
            "order_line__proposal_line__combination",
            "combination_item",
            "combination_item__product",
            "combination_item__product__supplier",
        )
        .order_by(
            "order_line__proposal_line__sort_order",
            "order_line__id",
            "combination_item__sort_order",
            "id",
        )
    )

    groups: "OrderedDict[tuple[int, str], Dict[str, Any]]" = OrderedDict()

    for oli in order_line_items:
        ol = oli.order_line
        pl = ol.proposal_line

        if oli.combination_item_id:
            product = oli.combination_item.product
            supplier = product.supplier if product else None
            label = (
                f"{product.brand or ''} {product.model_type or ''}".strip()
                or (product and str(product))
                or _("(Item)")
            )
            unit_price = None
            line_total = None
        else:
            product = pl.product if pl else None
            if pl.product_supplier_id and pl.product_supplier:
                supplier = pl.product_supplier.supplier
            else:
                supplier = pl.product.supplier if pl.product else None
            label = pl.name_snapshot or (
                pl.product
                and (
                    f"{pl.product.brand or ''} {pl.product.model_type or ''}".strip()
                    or str(pl.product)
                )
            ) or _("(Unknown)")
            unit_price = pl.unit_price_snapshot
            line_total = pl.line_total_snapshot

        key = (supplier.pk if supplier else 0, supplier.name if supplier else _("(No supplier)"))
        if key not in groups:
            groups[key] = {"supplier": supplier, "supplier_name": key[1], "rows": []}

        groups[key]["rows"].append(
            {
                "order_line_item": oli,
                "label": label,
                "product": product,
                "quantity": pl.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    return list(groups.values())


def update_proposal_client_crm_dept_contact_from_post(proposal, post: Dict[str, str]) -> None:
    """
    When the proposal has a client CRM organization, persist department and contact from
    order form fields `order_client_crm_department` and `order_client_crm_contact` (UUID or empty).

    Skips if those keys are absent (older forms). Runs `full_clean()` on the proposal.
    """
    if not proposal.client_crm_organization_id:
        return
    if "order_client_crm_department" not in post and "order_client_crm_contact" not in post:
        return

    org = proposal.client_crm_organization
    dept_raw = (post.get("order_client_crm_department") or "").strip()
    contact_raw = (post.get("order_client_crm_contact") or "").strip()

    proposal.client_crm_department = None
    proposal.client_crm_contact = None

    if dept_raw:
        try:
            du = uuid_lib.UUID(dept_raw)
            dept = Department.objects.get(uuid=du, organization=org)
            proposal.client_crm_department = dept
        except (ValueError, Department.DoesNotExist) as exc:
            raise ValidationError(
                {"order_client_crm_department": _("Invalid department for this company.")}
            ) from exc

    if contact_raw:
        try:
            cu = uuid_lib.UUID(contact_raw)
            m = OrganizationPerson.objects.select_related("department").get(
                uuid=cu, organization=org
            )
            proposal.client_crm_contact = m
        except (ValueError, OrganizationPerson.DoesNotExist) as exc:
            raise ValidationError(
                {"order_client_crm_contact": _("Invalid contact for this company.")}
            ) from exc

    proposal.full_clean()
    proposal.save()


def update_order_from_post(order: Order, post: Dict[str, str]) -> None:
    """
    Persist order-level status/note and per-OrderLineItem dates from a POST payload.
    Also updates proposal client CRM department/contact when posted from the order form.
    """
    proposal = order.proposal
    update_proposal_client_crm_dept_contact_from_post(proposal, post)

    update_order_fields: List[str] = []

    new_status = (post.get("order_status") or "").strip()
    if new_status in dict(Order.STATUS_CHOICES) and order.status != new_status:
        order.status = new_status
        update_order_fields.append("status")

    new_note = (post.get("order_note") or "").strip()
    if order.note != new_note:
        order.note = new_note
        update_order_fields.append("note")

    if update_order_fields:
        if "updated_at" not in update_order_fields:
            update_order_fields.append("updated_at")
        order.save(update_fields=update_order_fields)

    for oli in OrderLineItem.objects.filter(order_line__order=order):
        oli_key = str(oli.uuid)
        ordered_raw = (post.get(f"oli_{oli_key}_ordered", "") or "").strip()
        expected_raw = (post.get(f"oli_{oli_key}_expected", "") or "").strip()
        delivered_raw = (post.get(f"oli_{oli_key}_delivered", "") or "").strip()

        ordered_at = parse_datetime(ordered_raw) if ordered_raw else None
        expected_delivery = parse_date(expected_raw) if expected_raw else None
        delivered_at = parse_datetime(delivered_raw) if delivered_raw else None

        if (
            oli.ordered_at != ordered_at
            or oli.expected_delivery != expected_delivery
            or oli.delivered_at != delivered_at
        ):
            oli.ordered_at = ordered_at
            oli.expected_delivery = expected_delivery
            oli.delivered_at = delivered_at
            oli.save(update_fields=["ordered_at", "expected_delivery", "delivered_at"])

