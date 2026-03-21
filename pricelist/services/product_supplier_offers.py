"""
Multi-supplier catalog offers: serialize for proposal UI, pick by strategy, resolve FK for saves.
"""

from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from typing import Any

from pricelist.models import Product, ProductSupplier, round_price


def offer_dicts_for_product(product: Product, rounding: str) -> list[dict[str, Any]]:
    """JSON-serializable rows for the proposal supplier picker (unit_price rounded for display/JS)."""
    rows = list(product.product_suppliers.select_related("supplier").order_by("sort_order", "pk"))
    out: list[dict[str, Any]] = []
    for ps in rows:
        raw = product.sales_price_for_product_supplier(ps)
        out.append(
            {
                "uuid": str(ps.uuid),
                "supplier_id": ps.supplier_id,
                "supplier_name": ps.supplier.name,
                "unit_price": float(round_price(raw, rounding)) if raw is not None else None,
                "lead_time_days": ps.lead_time_days,
                "payment_terms": ps.payment_terms or "",
                "payment_terms_days": ps.payment_terms_days,
                "is_preferred": ps.is_preferred,
            }
        )
    return out


def pick_product_supplier(product: Product, strategy: str) -> ProductSupplier | None:
    """
    Choose one ProductSupplier row for bulk actions on the proposal page.

    Strategies: preferred, cheapest, fastest, best_payment (longest payment_terms_days).
    """
    rows = list(product.product_suppliers.select_related("supplier").order_by("sort_order", "pk"))
    if not rows:
        return None
    strategy = (strategy or "preferred").strip().lower()
    if strategy == "preferred":
        for ps in rows:
            if ps.is_preferred:
                return ps
        return rows[0]
    if strategy == "cheapest":

        def cheapest_key(ps: ProductSupplier):
            p = product.sales_price_for_product_supplier(ps)
            return (p is None, p if p is not None else Decimal("999999999999"))

        return min(rows, key=cheapest_key)
    if strategy == "fastest":

        def fastest_key(ps: ProductSupplier):
            lt = ps.lead_time_days
            return (lt is None, lt if lt is not None else 10**9)

        return min(rows, key=fastest_key)
    if strategy in ("best_payment", "best_terms", "payment"):

        def payment_key(ps: ProductSupplier):
            d = ps.payment_terms_days
            # Prefer larger days; nulls last
            return (d is None, -(d or 0))

        return min(rows, key=payment_key)
    return rows[0]


def get_product_supplier_for_product(product: Product, ps_uuid: str | None) -> ProductSupplier | None:
    """Resolve a catalog offer by stable UUID (never integer PK in HTTP/API)."""
    if not ps_uuid or not str(ps_uuid).strip():
        return None
    try:
        u = uuid_lib.UUID(str(ps_uuid).strip())
    except (ValueError, TypeError, AttributeError):
        return None
    try:
        return ProductSupplier.objects.select_related("supplier").get(uuid=u, product_id=product.pk)
    except ProductSupplier.DoesNotExist:
        return None


def resolve_supplier_for_proposal_line(product: Product, posted_ps_uuid: str | None) -> ProductSupplier | None:
    """
    Which offer to price a proposal line from: posted ProductSupplier UUID if valid,
    else preferred/single row, else None.
    """
    offers = list(product.product_suppliers.order_by("sort_order", "pk"))
    if not offers:
        return None
    if len(offers) == 1:
        return offers[0]
    if posted_ps_uuid:
        ps = get_product_supplier_for_product(product, posted_ps_uuid)
        if ps is not None:
            return ps
    return product.preferred_product_supplier()


def rounded_unit_price_for_product_supplier(product: Product, ps: ProductSupplier | None, rounding: str):
    """Catalog unit sales price (rounded) for the chosen offer; None if not priceable."""
    if ps is not None:
        raw = product.sales_price_for_product_supplier(ps)
    else:
        raw = product.calculated_sales_price
    if raw is None:
        return None
    return round_price(raw, rounding)
