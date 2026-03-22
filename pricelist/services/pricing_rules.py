"""Evaluate catalog sales price from profit profile decision tables (ordered rules, first match wins)."""

from __future__ import annotations

from decimal import Decimal

from ..models import ProfitProfile, SalesPricingRule


def _ordered_rules(profit_profile: ProfitProfile) -> list[SalesPricingRule]:
    """Return rules in evaluation order, using prefetch cache when present."""
    cache = getattr(profit_profile, "_prefetched_objects_cache", None)
    if cache and "sales_pricing_rules" in cache:
        return sorted(
            cache["sales_pricing_rules"],
            key=lambda r: (r.sort_order, r.pk),
        )
    return list(profit_profile.sales_pricing_rules.order_by("sort_order", "id"))


def _condition_matches(cost: Decimal, rule: SalesPricingRule) -> bool:
    if rule.is_fallback:
        return False
    op = rule.condition_operator
    lo = rule.condition_value
    hi = rule.condition_value_to
    if op == SalesPricingRule.OP_BETWEEN:
        if lo is None or hi is None:
            return False
        return cost >= lo and cost <= hi
    if lo is None:
        return False
    if op == SalesPricingRule.OP_LT:
        return cost < lo
    if op == SalesPricingRule.OP_LTE:
        return cost <= lo
    if op == SalesPricingRule.OP_GT:
        return cost > lo
    if op == SalesPricingRule.OP_GTE:
        return cost >= lo
    if op == SalesPricingRule.OP_EQ:
        return cost == lo
    return False


def _apply_markup(cost: Decimal, rule: "SalesPricingRule") -> Decimal:
    basis = cost * (Decimal("1.0") + (rule.markup_percentage / Decimal("100")))
    return basis + rule.markup_fixed


def sales_price_from_cost_and_profile(
    cost: Decimal | None,
    profit_profile: ProfitProfile | None,
    *,
    rules: QuerySet | None = None,
) -> Decimal | None:
    """
    Return unit sales price from cost and profit profile.
    Uses decision rules when profile.use_sales_pricing_rules is True and rules exist; otherwise flat markup.
    """
    if profit_profile is None or not profit_profile.is_active:
        return None
    if cost is None:
        return None

    if profit_profile.use_sales_pricing_rules:
        if rules is not None:
            rule_list = list(rules)
        else:
            rule_list = _ordered_rules(profit_profile)
        if rule_list:
            for rule in rule_list:
                if rule.is_fallback:
                    continue
                if _condition_matches(cost, rule):
                    return _apply_markup(cost, rule)
            for rule in rule_list:
                if rule.is_fallback:
                    return _apply_markup(cost, rule)
            return None

    basis = cost * (Decimal("1.0") + (profit_profile.markup_percentage / Decimal("100")))
    return basis + profit_profile.markup_fixed
