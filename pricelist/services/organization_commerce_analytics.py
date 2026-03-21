"""Order and invoice aggregates for a CRM organization (contact company detail)."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import CharField, Count, F, Sum, Value
from django.db.models.functions import Coalesce, ExtractYear
from django.utils import timezone
from django.utils.translation import gettext as gettext_fn

from ..models import Invoice, Order, ProposalLine


def _order_value(order) -> Decimal:
    if order.invoice_id:
        return order.invoice.grand_total_snapshot
    total = order.lines_total
    if total is None:
        return Decimal("0.00")
    return total


def compute_organization_commerce_analytics(organization) -> dict[str, Any]:
    """
    Turnover (invoiced), top purchased lines, and order activity by department and contact.
    Uses proposals linked to this organization; orders exclude cancelled.
    """
    org_id = organization.pk
    now = timezone.now()
    current_year = now.year
    last_year = current_year - 1
    year_start = current_year - 9
    years_range = list(range(year_start, current_year + 1))

    currency = (organization.currency or "").strip() or "EUR"

    # --- Turnover by calendar year (issued invoice preferred, else created) ---
    inv_qs = (
        Invoice.objects.filter(proposal__client_crm_organization_id=org_id)
        .exclude(status=Invoice.STATUS_CANCELLED)
        .annotate(
            y=ExtractYear(Coalesce("issued_at", "created_at")),
        )
        .values("y")
        .annotate(total=Sum("grand_total_snapshot"))
        .order_by("y")
    )
    turnover_map: dict[int, Decimal] = {}
    for row in inv_qs:
        y = row["y"]
        if y is None:
            continue
        turnover_map[int(y)] = row["total"] or Decimal("0.00")

    turnover_series: list[dict[str, Any]] = []
    for y in years_range:
        t = turnover_map.get(y, Decimal("0.00"))
        turnover_series.append({"year": y, "total": t})
    # Currency from latest invoice if org has none
    if currency == "EUR":
        sample = (
            Invoice.objects.filter(proposal__client_crm_organization_id=org_id)
            .exclude(status=Invoice.STATUS_CANCELLED)
            .order_by("-created_at")
            .values_list("currency_code", flat=True)
            .first()
        )
        if sample:
            currency = sample

    turnover_chart_json = json.dumps(
        {
            "labels": [str(x["year"]) for x in turnover_series],
            "values": [float(x["total"]) for x in turnover_series],
            "currency": currency,
        }
    )

    # --- Orders (value, dept, contact, year) ---
    order_qs = (
        Order.objects.filter(proposal__client_crm_organization_id=org_id)
        .exclude(status=Order.STATUS_CANCELLED)
        .select_related(
            "invoice",
            "proposal",
            "proposal__client_crm_department",
            "proposal__client_crm_contact",
            "proposal__client_crm_contact__person",
        )
        .annotate(
            lines_total=Sum("proposal__lines__line_total_snapshot"),
        )
    )
    order_list = list(order_qs)
    has_orders = bool(order_list)

    dept_orders: dict[int | None, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    dept_revenue: dict[int | None, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    person_orders: dict[int | None, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    person_revenue: dict[int | None, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    dept_names: dict[int | None, str] = {}
    person_labels: dict[int | None, str] = {}

    for o in order_list:
        y = o.created_at.year
        val = _order_value(o)
        prop = o.proposal
        d_id = prop.client_crm_department_id
        if d_id not in dept_names and d_id is not None:
            dept = prop.client_crm_department
            dept_names[d_id] = (dept.name if dept else "") or gettext_fn("Unnamed department")
        c_id = prop.client_crm_contact_id
        if c_id not in person_labels and c_id is not None:
            m = prop.client_crm_contact
            if m and m.person_id:
                p = m.person
                person_labels[c_id] = f"{p.first_name} {p.last_name}".strip() or gettext_fn("Unnamed contact")
            else:
                person_labels[c_id] = gettext_fn("Unnamed contact")

        dept_orders[d_id][y] += 1
        dept_revenue[d_id][y] += val
        if c_id is not None:
            person_orders[c_id][y] += 1
            person_revenue[c_id][y] += val

    none_label = gettext_fn("Unspecified")

    def rank_keys(
        counts: dict[int | None, dict[int, int]],
        revenue: dict[int | None, dict[int, Decimal]],
        names: dict[int | None, str],
        include_none: bool,
    ) -> list[int | None]:
        keys = [k for k in counts.keys() if k is not None]
        if include_none and None in counts:
            keys.append(None)
        keys.sort(
            key=lambda k: (
                -(counts[k].get(current_year, 0)),
                -(revenue[k].get(current_year, Decimal("0.00"))),
                -(counts[k].get(last_year, 0)),
                names.get(k, "") if k is not None else none_label,
            )
        )
        return keys[:3]

    dept_keys = rank_keys(dept_orders, dept_revenue, dept_names, include_none=True)
    person_keys = rank_keys(person_orders, person_revenue, person_labels, include_none=False)

    top_departments: list[dict[str, Any]] = []
    for k in dept_keys:
        label = none_label if k is None else dept_names.get(k, none_label)
        top_departments.append(
            {
                "label": label,
                "orders_this_year": dept_orders[k].get(current_year, 0),
                "orders_last_year": dept_orders[k].get(last_year, 0),
                "revenue_this_year": dept_revenue[k].get(current_year, Decimal("0.00")),
                "revenue_last_year": dept_revenue[k].get(last_year, Decimal("0.00")),
            }
        )

    top_people: list[dict[str, Any]] = []
    for k in person_keys:
        label = person_labels.get(k, gettext_fn("Unknown"))
        top_people.append(
            {
                "label": label,
                "orders_this_year": person_orders[k].get(current_year, 0),
                "orders_last_year": person_orders[k].get(last_year, 0),
                "revenue_this_year": person_revenue[k].get(current_year, Decimal("0.00")),
                "revenue_last_year": person_revenue[k].get(last_year, Decimal("0.00")),
            }
        )

    # --- Top proposal lines (products / combinations) on non-cancelled orders ---
    line_qs = (
        ProposalLine.objects.filter(
            proposal__order__isnull=False,
            proposal__client_crm_organization_id=org_id,
        )
        .exclude(proposal__order__status=Order.STATUS_CANCELLED)
        .annotate(
            label=Coalesce(
                F("product__name"),
                F("combination__name"),
                F("name_snapshot"),
            )
        )
        .values("line_type", "product_id", "combination_id", "label")
        .annotate(
            revenue=Sum("line_total_snapshot"),
            orders=Count("proposal__order", distinct=True),
        )
        .order_by("-revenue")[:3]
    )

    top_lines: list[dict[str, Any]] = []
    for row in line_qs:
        lbl = (row.get("label") or "").strip() or gettext_fn("(Unnamed line)")
        lt = row.get("line_type") or ""
        type_display = (
            gettext_fn("Combination")
            if lt == ProposalLine.LINE_TYPE_COMBINATION
            else gettext_fn("Product")
        )
        top_lines.append(
            {
                "label": lbl,
                "line_type_display": type_display,
                "revenue": row.get("revenue") or Decimal("0.00"),
                "orders": row.get("orders") or 0,
            }
        )

    has_invoices = Invoice.objects.filter(
        proposal__client_crm_organization_id=org_id,
    ).exclude(status=Invoice.STATUS_CANCELLED).exists()

    return {
        "currency": currency,
        "current_year": current_year,
        "last_year": last_year,
        "turnover_series": turnover_series,
        "turnover_chart_json": turnover_chart_json,
        "top_lines": top_lines,
        "top_departments": top_departments,
        "top_people": top_people,
        "has_orders": has_orders,
        "has_invoices": has_invoices,
        "has_commerce_data": has_orders or has_invoices,
    }
