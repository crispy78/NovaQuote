import uuid as uuid_module
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from django.db.models import F, Prefetch, Q
from django.utils.translation import gettext as _

from .models import (
    Category,
    Combination,
    CombinationItem,
    ContractDuration,
    Department,
    Order,
    OrderLine,
    OrderLineItem,
    Organization,
    OrganizationPerson,
    OrganizationRole,
    Product,
    ProductOption,
    ProductSupplier,
    Proposal,
    ProposalContractSnapshot,
    ProposalHistory,
    ProposalLine,
    ProposalLineOption,
    format_number_with_separators,
    get_general_settings,
    price_decimal_places,
    round_price,
)
from .services.invoice_service import (
    get_invoice_for_proposal,
    proposal_allows_order_creation,
)

from .services.crm_contact_payload import (
    client_lead_contact_picker_payload,
    single_organization_client_picker_payload,
)
from .services.product_supplier_offers import (
    offer_dicts_for_product,
    resolve_supplier_for_proposal_line,
    rounded_unit_price_for_product_supplier,
)
from .services.order_service import (
    build_supplier_groups,
    create_order_from_proposal,
    update_order_from_post,
)


def _organization_has_client_or_lead_role(org: Organization) -> bool:
    codes = set(org.role_assignments.values_list("role", flat=True))
    return OrganizationRole.ROLE_CLIENT in codes or OrganizationRole.ROLE_LEAD in codes


def set_proposal_client_crm_from_post(request, proposal: Proposal) -> None:
    """Set proposal client/lead CRM FKs from POST (UUID strings). Clears when empty."""
    proposal.client_crm_organization = None
    proposal.client_crm_department = None
    proposal.client_crm_contact = None
    org_uuid = (request.POST.get("client_crm_organization") or "").strip()
    dept_uuid = (request.POST.get("client_crm_department") or "").strip()
    contact_uuid = (request.POST.get("client_crm_contact") or "").strip()
    org = None
    if org_uuid:
        try:
            u = uuid_module.UUID(org_uuid)
            org = Organization.objects.prefetch_related("role_assignments").get(uuid=u)
        except (ValueError, TypeError, Organization.DoesNotExist):
            org = None
    if org and _organization_has_client_or_lead_role(org):
        proposal.client_crm_organization = org
    if org and dept_uuid:
        try:
            du = uuid_module.UUID(dept_uuid)
            dept = Department.objects.get(uuid=du, organization=org)
            proposal.client_crm_department = dept
        except (ValueError, TypeError, Department.DoesNotExist):
            pass
    if org and contact_uuid:
        try:
            cu = uuid_module.UUID(contact_uuid)
            m = OrganizationPerson.objects.select_related("department").get(uuid=cu, organization=org)
            proposal.client_crm_contact = m
        except (ValueError, TypeError, OrganizationPerson.DoesNotExist):
            pass


def _get_price_list_context(selected_category_slug=None):
    products_qs = (
        Product.objects.filter(show_in_price_list=True)
        .select_related("supplier", "category", "profit_profile")
        .prefetch_related(
            Prefetch(
                "product_suppliers",
                queryset=ProductSupplier.objects.select_related("supplier").order_by("sort_order", "pk"),
            ),
            Prefetch(
                "option_lines",
                queryset=ProductOption.objects.select_related("option_product", "option_product__profit_profile").order_by("sort_order"),
            ),
        )
    )
    categories = Category.objects.all()

    selected_category = None
    if selected_category_slug:
        try:
            # Resolve by UUID first, then by pk (backwards compatibility)
            try:
                uuid_module.UUID(str(selected_category_slug))
                selected_category = categories.get(uuid=selected_category_slug)
            except (ValueError, TypeError, Category.DoesNotExist):
                selected_category = categories.get(pk=selected_category_slug)
            products_qs = products_qs.filter(category=selected_category)
        except (Category.DoesNotExist, ValueError):
            selected_category = None

    products = products_qs.order_by(F("category__sort_order").asc(nulls_last=True), "name")
    combinations = (
        Combination.objects.prefetch_related(
            "products",
            Prefetch(
                "items",
                queryset=CombinationItem.objects.select_related("product", "product__profit_profile").prefetch_related(
                    Prefetch("selected_options", queryset=Product.objects.select_related("profit_profile")),
                    "product__option_lines",
                ).order_by("sort_order"),
            ),
        )
        .all()
        .order_by("name")
    )
    return {
        "products": products,
        "combinations": combinations,
        "categories": categories,
        "selected_category": selected_category,
        "settings": get_general_settings(),
    }


def home_view(request):
    """Landing page with link to price list and proposal."""
    return render(request, "pricelist/home.html", {"settings": get_general_settings()})


def price_list_view(request):
    """Full price list: products and combinations."""
    category_id = request.GET.get("category")
    context = _get_price_list_context(selected_category_slug=category_id)
    context["price_list_section"] = "all"
    return render(request, "pricelist/price_list.html", context)


def price_list_products_view(request):
    """Price list: standalone products only."""
    category_id = request.GET.get("category")
    context = _get_price_list_context(selected_category_slug=category_id)
    context["price_list_section"] = "products"
    context["combinations"] = []
    return render(request, "pricelist/price_list.html", context)


def price_list_combinations_view(request):
    """Price list: packages / combinations only."""
    context = _get_price_list_context()
    context["price_list_section"] = "combinations"
    context["products"] = []
    context["categories"] = []
    context["selected_category"] = None
    return render(request, "pricelist/price_list.html", context)


def proposal_view(request):
    """
    Proposal (calculatie) page: combinations, simple products (qty), and configurable products
    (one row per unit with option dropdowns). Builds proposal_simple_lines (with combination_items
    for package contents) and proposal_configurable_products for the cart. Can load a saved proposal via ?load=uuid.
    """
    context = _get_price_list_context()
    settings = context["settings"]
    rounding = getattr(settings, "rounding", "0.01") or "0.01"

    # Which products have options (for splitting simple vs configurable when loading saved)
    products_with_options = {p.pk for p in context["products"] if p.option_lines.exists()}

    saved_proposal = None
    saved_quantities = {}  # (type, id) -> quantity for simple lines (id = product pk or combination pk internally)
    saved_configurable_rows = {}  # product_id -> [ {option_article_numbers, product_supplier_uuid}, ... ]
    saved_product_supplier_uuid = {}  # product_id -> ProductSupplier UUID string when loading saved
    load_id = request.GET.get("load")
    if load_id:
        try:
            saved_proposal = _get_proposal_from_identifier(
                load_id,
                Proposal.objects.select_related(
                    "client_crm_organization",
                    "client_crm_department",
                    "client_crm_contact__person",
                ).prefetch_related(
                    Prefetch(
                        "lines",
                        queryset=ProposalLine.objects.select_related("product_supplier__supplier").prefetch_related(
                            "selected_options"
                        ).order_by("sort_order", "id"),
                    ),
                ),
            )
            for line in saved_proposal.lines.order_by("sort_order", "id"):
                if line.line_type == ProposalLine.LINE_TYPE_COMBINATION:
                    key = ("combination", line.combination_id)
                    if key[1]:
                        saved_quantities[key] = saved_quantities.get(key, 0) + line.quantity
                else:
                    pid = line.product_id
                    if not pid:
                        continue
                    if pid in products_with_options:
                        option_ids = list(line.selected_options.values_list("option_product_id", flat=True))
                        opt_map = dict(
                            Product.objects.filter(pk__in=option_ids).values_list("pk", "article_number")
                        )
                        option_article_numbers = [str(opt_map[oid]) for oid in option_ids if oid in opt_map]
                        ps_uuid_str = (
                            str(line.product_supplier.uuid) if line.product_supplier_id else None
                        )
                        for _unused in range(max(1, int(line.quantity))):
                            saved_configurable_rows.setdefault(pid, []).append(
                                {
                                    "option_article_numbers": option_article_numbers,
                                    "product_supplier_uuid": ps_uuid_str,
                                }
                            )
                    else:
                        key = ("product", pid)
                        saved_quantities[key] = saved_quantities.get(key, 0) + line.quantity
                        if pid not in saved_product_supplier_uuid:
                            saved_product_supplier_uuid[pid] = (
                                str(line.product_supplier.uuid) if line.product_supplier_id else None
                            )
        except Http404:
            saved_proposal = None

    # Build simple lines: combinations (with contents for display) + products that have no options
    proposal_simple_lines = []
    for comb in context["combinations"]:
        price = comb.offer_price
        if price is not None:
            qty = saved_quantities.get(("combination", comb.pk), 0) if saved_proposal else 0
            # List each product in the combination and its selected options, for display under the package name
            combination_items = []
            for item in comb.items.all():
                label = f"{item.product.brand or ''} {item.product.model_type or ''}".strip() or item.product.name or str(item.product)
                option_labels = [f"{p.brand or ''} {p.model_type or ''}".strip() or str(p) for p in item.selected_options.all()]
                combination_items.append({"label": label, "options": option_labels})
            proposal_simple_lines.append({
                "type": "combination",
                "entity_uuid": str(comb.uuid),
                "name": comb.name,
                "unit_price": round_price(price, rounding),
                "initial_quantity": qty,
                "combination_items": combination_items,
            })
    for product in context["products"]:
        if product.pk in products_with_options:
            continue
        posted_ps_uuid = saved_product_supplier_uuid.get(product.pk) if saved_proposal else None
        ps = resolve_supplier_for_proposal_line(product, posted_ps_uuid)
        unit = rounded_unit_price_for_product_supplier(product, ps, rounding)
        if unit is not None:
            label = f"{product.brand or ''} {product.model_type or ''}".strip() or product.name or str(product)
            qty = saved_quantities.get(("product", product.pk), 0) if saved_proposal else 0
            offers = offer_dicts_for_product(product, rounding)
            proposal_simple_lines.append({
                "type": "product",
                "entity_uuid": str(product.article_number),
                "name": label or _("Product"),
                "unit_price": unit,
                "initial_quantity": qty,
                "supplier_offers": offers,
                "initial_product_supplier_uuid": str(ps.uuid) if ps else "",
                "multi_supplier": len(offers) > 1,
            })

    # Configurable products: one or more rows per product, each row = one unit with selected options
    proposal_configurable_products = []
    for product in context["products"]:
        if product.pk not in products_with_options:
            continue
        if product.calculated_sales_price is None:
            continue
        label = f"{product.brand or ''} {product.model_type or ''}".strip() or product.name or str(product)
        options = []
        for opt in product.option_lines.all():
            opt_price = opt.option_product.calculated_sales_price
            options.append(
                {
                    "article_number": str(opt.option_product.article_number),
                    "label": opt.short_description.strip() or str(opt.option_product),
                    "unit_price": float(round_price(opt_price, rounding)) if opt_price is not None else 0.0,
                }
            )
        offers = offer_dicts_for_product(product, rounding)
        normalized_rows = saved_configurable_rows.get(product.pk) or [
            {"option_article_numbers": [], "product_supplier_uuid": None}
        ]
        rows_render = []
        for row in normalized_rows:
            if not isinstance(row, dict):
                row = {"option_article_numbers": [], "product_supplier_uuid": None}
            row_ps_uuid = row.get("product_supplier_uuid")
            ps = resolve_supplier_for_proposal_line(product, row_ps_uuid)
            base_unit = rounded_unit_price_for_product_supplier(product, ps, rounding)
            if base_unit is None:
                base_unit = round_price(product.calculated_sales_price, rounding)
            rows_render.append({
                "option_article_numbers": row.get("option_article_numbers") or [],
                "product_supplier_uuid": row_ps_uuid,
                "base_unit_price": base_unit,
                "resolved_product_supplier_uuid": str(ps.uuid) if ps else "",
            })
        default_unit = round_price(product.calculated_sales_price, rounding)
        proposal_configurable_products.append({
            "product_entity_uuid": str(product.article_number),
            "name": label or _("Product"),
            "unit_price": default_unit,
            "options": options,
            "initial_rows": rows_render,
            "supplier_offers": offers,
            "multi_supplier": len(offers) > 1,
        })

    def _product_supplier_count(prod):
        cache = getattr(prod, "_prefetched_objects_cache", None)
        if cache and "product_suppliers" in cache:
            return len(cache["product_suppliers"])
        return prod.product_suppliers.count()

    product_supplier_offers_map = {}
    for product in context["products"]:
        offers = offer_dicts_for_product(product, rounding)
        if offers:
            product_supplier_offers_map[str(product.article_number)] = offers

    context["proposal_simple_lines"] = proposal_simple_lines
    context["proposal_configurable_products"] = proposal_configurable_products
    context["product_supplier_offers"] = product_supplier_offers_map
    context["proposal_show_supplier_column"] = any(_product_supplier_count(p) > 1 for p in context["products"])
    context["saved_proposal"] = saved_proposal
    context["proposal_contact_picker"] = client_lead_contact_picker_payload()
    # Pass separators for JS number formatting (settings.decimal_sep/thousands_sep are callables)
    ds = getattr(settings, "decimal_sep", None)
    ts = getattr(settings, "thousands_sep", None)
    context["proposal_decimal_sep"] = ds() if callable(ds) else ","
    context["proposal_thousands_sep"] = ts() if callable(ts) else "."
    # Active contract durations for maintenance contract options (proposal)
    active_durations = ContractDuration.objects.filter(is_active=True).order_by("duration_months")
    context["active_contract_durations"] = [
        {
            "name": d.name,
            "duration_months": d.duration_months,
            "hardware_fee_percentage": float(d.hardware_fee_percentage),
            "visits_per_contract": float(d.visits_per_contract),
        }
        for d in active_durations
    ]
    # Maintenance calculation settings (for JS; visits_per_contract is per duration)
    context["maintenance_settings"] = {
        "time_per_product_minutes": float(getattr(settings, "time_per_product_minutes", 15) or 15),
        "minimum_visit_minutes": float(getattr(settings, "minimum_visit_minutes", 60) or 60),
        "hourly_rate": float(getattr(settings, "hourly_rate", 75) or 75),
        "show_contract_fee_calculation": bool(getattr(settings, "show_contract_fee_calculation", False)),
    }
    context["show_contract_fee_calculation"] = context["maintenance_settings"]["show_contract_fee_calculation"]
    # Translated strings for the contract calculation breakdown (used in JS)
    context["proposal_calc_i18n"] = {
        "of_purchase_value": _("of purchase value"),
        "per_visit": _("per visit"),
        "product_s": _("product(s)"),
        "above_minimum": _("Above minimum of {min} min."),
        "below_minimum": _("Below minimum of {min} min, so we use {min} min."),
        "hourly_rate": _("hourly rate"),
        "visits_in_contract_period": _("visits in contract period"),
    }
    return render(request, "pricelist/proposal.html", context)


def _format_price_pdf(value, settings):
    """Format a price for the PDF using currency, rounding and separators from settings."""
    if value is None:
        return None
    r = round_price(value, getattr(settings, "rounding", None) or "0.01")
    currency = (getattr(settings, "currency", None) or "EUR").strip()
    dec = price_decimal_places(getattr(settings, "rounding", None) or "0.01")
    decimal_sep = settings.decimal_sep() if hasattr(settings, "decimal_sep") and callable(getattr(settings, "decimal_sep")) else ","
    thousands_sep = settings.thousands_sep() if hasattr(settings, "thousands_sep") and callable(getattr(settings, "thousands_sep")) else "."
    formatted = format_number_with_separators(r, dec, decimal_sep, thousands_sep)
    return f"{currency} {formatted}"


def price_list_pdf_view(request):
    """Generate a simple PDF view of the price list with reportlab (no external binaries)."""
    context = _get_price_list_context()
    settings = context["settings"]
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 2 * cm
    y = height - 2 * cm

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(x_margin, y, _("NovaQuote"))
    y -= 1 * cm

    # Standalone products
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x_margin, y, _("Standalone products"))
    y -= 0.6 * cm
    p.setStrokeColor(colors.black)
    p.line(x_margin, y, width - x_margin, y)
    y -= 0.5 * cm

    p.setFont("Helvetica", 9)
    for product in context["products"]:
        lines = []
        name_part = f"{product.brand or ''} {product.model_type or ''}".strip() or f"Product #{product.pk}"
        supplier_name = product.supplier.name if product.supplier else "-"
        lines.append(f"{name_part} ({_('Supplier')}: {supplier_name})")
        if product.description:
            lines.append(product.description)
        if product.calculated_sales_price is not None:
            lines.append(f"{_('Sales price')}: {_format_price_pdf(product.calculated_sales_price, settings)}")
        for line in product.option_lines.all():
            option = line.option_product
            option_name = line.short_description.strip() or f"{option.brand or ''} {option.model_type or ''}".strip() or f"Option #{option.pk}"
            price_str = _format_price_pdf(option.calculated_sales_price, settings) if option.calculated_sales_price is not None else "-"
            lines.append(f"  {_('Option')}: {option_name} - {price_str}")
        if product.price_last_changed:
            lines.append(f"{_('Price last changed')}: {product.price_last_changed.strftime('%d-%m-%Y')}")

        for line in lines:
            if y < 2 * cm:
                p.showPage()
                y = height - 2 * cm
                p.setFont("Helvetica", 9)
            p.drawString(x_margin, y, line)
            y -= 0.45 * cm

        # Blank line between products
        y -= 0.3 * cm

    # New page for combinations if little space left
    if y < 4 * cm:
        p.showPage()
        y = height - 2 * cm

    # Combinations
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x_margin, y, _("Packages / Combinations"))
    y -= 0.6 * cm
    p.setStrokeColor(colors.black)
    p.line(x_margin, y, width - x_margin, y)
    y -= 0.5 * cm

    p.setFont("Helvetica", 9)
    for combination in context["combinations"]:
        lines = []
        lines.append(combination.name)
        if combination.description:
            lines.append(combination.description)

        item_lines = []
        if combination.items.exists():
            for item in combination.items.all():
                item_price = item.item_price()
                item_name = f"{item.product.brand or ''} {item.product.model_type or ''}".strip() or f"Product #{item.product.pk}"
                item_lines.append(f"- {item_name} ({_format_price_pdf(item_price, settings)})")
                for option in item.selected_options.all():
                    option_lines = [r for r in item.product.option_lines.all() if r.option_product_id == option.pk]
                    label = (option_lines[0].short_description.strip() if option_lines and option_lines[0].short_description else f"{option.brand or ''} {option.model_type or ''}".strip()) or str(option)
                    item_lines.append(f"    - {label}")
        else:
            for product in combination.products.all():
                line = f"- {product.brand or ''} {product.model_type or ''}".strip() or str(product)
                if product.calculated_sales_price is not None:
                    line += f" ({_format_price_pdf(product.calculated_sales_price, settings)})"
                item_lines.append(line)
        if item_lines:
            lines.append(_("In this package") + ":")
            lines.extend(item_lines)

        orig = combination.original_price
        lines.append(f"{_('From')}: {_format_price_pdf(orig, settings)}")
        lines.append(f"{_('Offer price')}: {_format_price_pdf(combination.offer_price, settings)}")

        if combination.date_range:
            lines.append(f"{_('Price changes within this package')}: {combination.date_range}")

        for line in lines:
            if y < 2 * cm:
                p.showPage()
                y = height - 2 * cm
                p.setFont("Helvetica", 9)
            p.drawString(x_margin, y, line)
            y -= 0.45 * cm

        # Extra space between combinations
        y -= 0.4 * cm

    p.showPage()
    p.save()

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename=\"novaquote_price_list.pdf\"'
    return response


def product_detail_view(request, uuid):
    """
    Detail page for one product; reuses the same styling and currency settings as the price list.
    """
    gen_settings = get_general_settings()
    qs = (
        Product.objects.filter(article_number=uuid)
        .select_related(
            "supplier",
            "category",
            "profit_profile",
            "supplier_crm_organization",
            "supplier_crm_department",
            "supplier_crm_contact__person",
        )
        .prefetch_related(
            Prefetch(
                "product_suppliers",
                queryset=ProductSupplier.objects.select_related("supplier").order_by("sort_order", "pk"),
            ),
            Prefetch(
                "option_lines",
                queryset=ProductOption.objects.select_related("option_product", "option_product__profit_profile").order_by("sort_order"),
            ),
        )
        .order_by("pk")
    )
    product = qs.first()
    if product is None:
        from django.http import Http404
        raise Http404(_("No product with this article number."))
    combinations = Combination.objects.filter(
        Q(products=product) | Q(items__product=product)
    ).distinct()

    def sales_from_cost(prod, cost_decimal):
        if prod.fixed_sales_price is not None:
            return float(prod.fixed_sales_price)
        if not prod.profit_profile or not prod.profit_profile.is_active:
            return None
        from decimal import Decimal
        basis = cost_decimal * (Decimal("1.0") + (prod.profit_profile.markup_percentage / Decimal("100")))
        return float(basis + prod.profit_profile.markup_fixed)

    show_chart = getattr(gen_settings, "show_price_history_chart_on_product_page", False)
    show_cost = getattr(gen_settings, "show_cost_in_price_history_chart", True)
    show_sales = getattr(gen_settings, "show_sales_in_price_history_chart", False)
    price_history_data = []
    if show_chart and (show_cost or show_sales):
        history = list(
            product.price_history.order_by("change_date").values_list(
                "change_date", "new_cost_price", "sales_price_at_date"
            )
        )
        for row in history:
            d, cost, sales_at_date = row[0], row[1], row[2]
            point = {"date": d.isoformat()}
            if show_cost:
                point["cost"] = float(cost)
            if show_sales:
                v = float(sales_at_date) if sales_at_date is not None else sales_from_cost(product, cost)
                if v is not None:
                    point["sales"] = v
            price_history_data.append(point)
        if product.cost_price is not None and product.price_last_changed:
            last_date = history[-1][0] if history else None
            if last_date != product.price_last_changed:
                point = {"date": product.price_last_changed.isoformat()}
                if show_cost:
                    point["cost"] = float(product.cost_price)
                if show_sales:
                    v = sales_from_cost(product, product.cost_price)
                    if v is not None:
                        point["sales"] = v
                price_history_data.append(point)
                price_history_data.sort(key=lambda x: x["date"])
    context = {
        "product": product,
        "settings": gen_settings,
        "combinations": combinations,
        "show_price_history_chart": show_chart and (show_cost or show_sales) and price_history_data,
        "show_price_history_cost": show_cost,
        "show_price_history_sales": show_sales,
        "price_history_data": price_history_data,
    }
    return render(request, "pricelist/product_detail.html", context)


# ----- Saved proposals (calculations) -----


def _get_proposal_from_identifier(identifier, queryset=None):
    """
    Resolve identifier to a Proposal. Tries as UUID first; if not a valid UUID, looks up by
    exact reference (most recently updated if multiple matches). Used for proposal detail, save, order create.
    """
    if queryset is None:
        queryset = Proposal.objects.all()
    # Try as UUID
    try:
        uuid_module.UUID(str(identifier))
        return get_object_or_404(queryset, uuid=identifier)
    except (ValueError, TypeError):
        pass
    # Try as reference (exact match; if multiple, most recently updated)
    proposal = queryset.filter(reference=identifier).order_by("-updated_at").first()
    if proposal is None:
        raise Http404(_("No saved proposal found with this identifier or reference."))
    return proposal


def _proposal_context_from_proposal(proposal, settings):
    """
    Build a list of line dicts and grand total from a saved Proposal for the proposal detail view.
    Each line includes combination_items (product + options per item) when the line is a combination,
    so the template can show package contents.
    """
    lines = []
    total_value = Decimal("0.00")
    total_products = 0
    for line in proposal.lines.order_by("sort_order", "id"):
        sup_label = ""
        if line.line_type == ProposalLine.LINE_TYPE_PRODUCT:
            sup_label = (line.supplier_name_snapshot or "").strip()
            if not sup_label and line.product_supplier_id and hasattr(line, "product_supplier") and line.product_supplier:
                sup_label = line.product_supplier.supplier.name
        line_dict = {
            "type": line.line_type,
            "id": line.combination_id if line.line_type == ProposalLine.LINE_TYPE_COMBINATION else line.product_id,
            "name": line.name_snapshot or _("(Unknown item)"),
            "unit_price": line.unit_price_snapshot,
            "quantity": line.quantity,
            "line_total": line.line_total_snapshot,
            "is_removed": line.is_removed,
            "supplier_name": sup_label,
        }
        # For combination lines, attach list of products + option labels for display on saved proposal detail
        if line.line_type == ProposalLine.LINE_TYPE_COMBINATION and line.combination_id and hasattr(line, "combination") and line.combination:
            combination_items = []
            for item in line.combination.items.all():
                label = f"{item.product.brand or ''} {item.product.model_type or ''}".strip() or (item.product.name if item.product else "") or _("(Item)")
                option_labels = [f"{p.brand or ''} {p.model_type or ''}".strip() or str(p) for p in item.selected_options.all()]
                combination_items.append({"label": label, "options": option_labels})
            line_dict["combination_items"] = combination_items
        else:
            line_dict["combination_items"] = []
        lines.append(line_dict)
        total_value += line.line_total_snapshot
        total_products += int(line.quantity) if line.quantity else 0
    grand_total = proposal.grand_total_snapshot()
    return {"lines": lines, "grand_total": grand_total, "total_value": total_value, "total_products": total_products}


@require_http_methods(["GET", "POST"])
def proposal_save_view(request):
    """Save current calculation: POST with reference and lines (type, id, quantity, unit_price)."""
    if request.method != "POST":
        return redirect("pricelist:proposal")
    reference = (request.POST.get("reference") or "").strip()
    proposal_uuid_raw = (request.POST.get("proposal_uuid") or "").strip()
    # Parse lines: line_0_type, line_0_id (product article_number or combination uuid), qty, unit_price,
    # line_0_options (comma-separated option product article_number UUIDs), line_0_product_supplier (ProductSupplier uuid)
    lines_data = []
    i = 0
    while True:
        t = request.POST.get(f"line_{i}_type")
        if t not in ("product", "combination"):
            break
        line_id_raw = (request.POST.get(f"line_{i}_id", "") or "").strip()
        try:
            qty = request.POST.get(f"line_{i}_qty", "0")
            unit = request.POST.get(f"line_{i}_unit_price", "0")
            options_raw = request.POST.get(f"line_{i}_options", "")
            option_article_keys = [x.strip() for x in options_raw.split(",") if x.strip()]
            ps_raw = (request.POST.get(f"line_{i}_product_supplier") or "").strip()
            product_supplier_uuid = ps_raw if ps_raw else None
            qty_dec = Decimal(str(qty))
            unit_dec = Decimal(str(unit))
        except (ValueError, TypeError, ArithmeticError):
            i += 1
            continue
        if not line_id_raw or qty_dec <= 0:
            i += 1
            continue
        try:
            entity_u = uuid_module.UUID(line_id_raw)
        except (ValueError, TypeError, AttributeError):
            i += 1
            continue
        if t == "combination":
            try:
                comb = Combination.objects.get(uuid=entity_u)
            except Combination.DoesNotExist:
                i += 1
                continue
            lines_data.append(
                {
                    "type": t,
                    "product_id": None,
                    "combination_id": comb.pk,
                    "quantity": qty_dec,
                    "unit_price": unit_dec,
                    "option_article_keys": [],
                    "product_supplier_uuid": None,
                }
            )
        else:
            try:
                prod = Product.objects.get(article_number=entity_u)
            except Product.DoesNotExist:
                i += 1
                continue
            lines_data.append(
                {
                    "type": t,
                    "product_id": prod.pk,
                    "combination_id": None,
                    "quantity": qty_dec,
                    "unit_price": unit_dec,
                    "option_article_keys": option_article_keys,
                    "product_supplier_uuid": product_supplier_uuid,
                }
            )
        i += 1
    if not lines_data:
        return redirect("pricelist:proposal")
    settings = get_general_settings()
    rounding = getattr(settings, "rounding", "0.01") or "0.01"
    user = request.user if request.user.is_authenticated else None

    proposal = None
    action = None
    if proposal_uuid_raw:
        try:
            uuid_module.UUID(proposal_uuid_raw)
            proposal = Proposal.objects.get(uuid=proposal_uuid_raw)
        except (ValueError, Proposal.DoesNotExist):
            proposal = None
        if not proposal:
            return redirect("pricelist:proposal")
        action = ProposalHistory.ACTION_EDITED
    else:
        action = ProposalHistory.ACTION_CREATED

    try:
        with transaction.atomic():
            if proposal_uuid_raw:
                proposal.reference = reference or proposal.reference
                proposal.lines.all().delete()
            else:
                proposal = Proposal.objects.create(
                    reference=reference,
                    created_by=user,
                )

            sort_order = 0
            for row in lines_data:
                name_snapshot = ""
                if row["type"] == "combination":
                    try:
                        comb = Combination.objects.get(pk=row["combination_id"])
                        name_snapshot = comb.name
                    except Combination.DoesNotExist:
                        name_snapshot = _("(Removed combination)")
                else:
                    try:
                        prod = Product.objects.get(pk=row["product_id"])
                        name_snapshot = f"{prod.brand or ''} {prod.model_type or ''}".strip() or prod.name or str(prod)
                    except Product.DoesNotExist:
                        name_snapshot = _("(Removed product)")
                unit_price = row["unit_price"]
                product_supplier_obj = None
                supplier_name_snapshot = ""
                if row["type"] == "product":
                    try:
                        prod = Product.objects.prefetch_related(
                            Prefetch(
                                "product_suppliers",
                                queryset=ProductSupplier.objects.select_related("supplier").order_by("sort_order", "pk"),
                            )
                        ).get(pk=row["product_id"])
                        product_supplier_obj = resolve_supplier_for_proposal_line(
                            prod, row.get("product_supplier_uuid")
                        )
                        server_unit = rounded_unit_price_for_product_supplier(prod, product_supplier_obj, rounding)
                        if server_unit is not None:
                            unit_price = server_unit
                        if product_supplier_obj and product_supplier_obj.supplier_id:
                            supplier_name_snapshot = product_supplier_obj.supplier.name
                        elif prod.supplier_id:
                            supplier_name_snapshot = prod.supplier.name
                    except Product.DoesNotExist:
                        pass
                line_total = round_price(row["quantity"] * unit_price, rounding)
                proposal_line = ProposalLine.objects.create(
                    proposal=proposal,
                    sort_order=sort_order,
                    line_type=row["type"],
                    product_id=row["product_id"] if row["type"] == "product" else None,
                    combination_id=row["combination_id"] if row["type"] == "combination" else None,
                    quantity=row["quantity"],
                    unit_price_snapshot=unit_price,
                    line_total_snapshot=line_total,
                    name_snapshot=name_snapshot or _("Item"),
                    product_supplier=product_supplier_obj,
                    supplier_name_snapshot=supplier_name_snapshot,
                )
                for opt_key in row.get("option_article_keys") or []:
                    try:
                        opt_prod = Product.objects.get(article_number=uuid_module.UUID(opt_key))
                        ProposalLineOption.objects.get_or_create(
                            proposal_line=proposal_line,
                            option_product_id=opt_prod.pk,
                        )
                    except (ValueError, Product.DoesNotExist):
                        pass
                sort_order += 1

            proposal.time_per_product_snapshot = getattr(settings, "time_per_product_minutes", None) or Decimal("15")
            proposal.minimum_visit_snapshot = getattr(settings, "minimum_visit_minutes", None) or Decimal("60")
            proposal.hourly_rate_snapshot = getattr(settings, "hourly_rate", None) or Decimal("75")
            set_proposal_client_crm_from_post(request, proposal)
            proposal.full_clean()
            proposal.save()

            proposal.contract_snapshots.all().delete()
            for snap_order, duration in enumerate(
                ContractDuration.objects.filter(is_active=True).order_by("duration_months")
            ):
                ProposalContractSnapshot.objects.create(
                    proposal=proposal,
                    contract_duration=duration,
                    contract_duration_uuid=duration.uuid,
                    sort_order=snap_order,
                    name=duration.name,
                    duration_months=duration.duration_months,
                    hardware_fee_percentage=duration.hardware_fee_percentage,
                    visits_per_contract=duration.visits_per_contract,
                )

            ProposalHistory.objects.create(
                proposal=proposal,
                action=action,
                description=_("Reference: %(ref)s") % {"ref": reference or proposal.reference or "-"},
                user=user,
                details={"lines_count": len(lines_data)},
            )
    except ValidationError:
        messages.error(
            request,
            _("Could not save the selected client contact. Please check company, department, and person."),
        )
        return redirect("pricelist:proposal")

    return redirect("pricelist:proposal_detail", identifier=proposal.uuid)


def proposal_list_view(request):
    """List saved proposals (calculations)."""
    proposals = Proposal.objects.prefetch_related("lines").order_by("-updated_at")[:200]
    settings = get_general_settings()
    context = {"proposals": proposals, "settings": settings}
    return render(request, "pricelist/proposal_list.html", context)


def proposal_detail_view(request, identifier):
    """View one saved proposal (identifier = UUID or reference)."""
    proposal = _get_proposal_from_identifier(
        identifier,
        Proposal.objects.select_related(
            "order",
            "invoice",
            "client_crm_organization",
            "client_crm_department",
            "client_crm_contact__person",
        ).prefetch_related(
            "lines",
            "lines__product_supplier__supplier",
            "lines__combination__items__product",
            "lines__combination__items__selected_options",
            "contract_snapshots",
        ),
    )
    settings = get_general_settings()
    data = _proposal_context_from_proposal(proposal, settings)
    # Match by UUID so "contract A" (deleted) is not confused with new "contract C" (same name)
    active_durations_current = list(
        ContractDuration.objects.filter(is_active=True).order_by("duration_months")
    )
    active_uuids = {d.uuid for d in active_durations_current}
    current_duration_by_uuid = {d.uuid: d for d in active_durations_current}
    # Single pass over ordered snapshots: build snapshot list and UUID set
    ordered_snapshots = list(proposal.contract_snapshots.order_by("sort_order", "id"))
    snapshot_uuids = {s.contract_duration_uuid for s in ordered_snapshots if s.contract_duration_uuid}
    # Contract options from snapshot (as at save time): is_removed by UUID, is_modified when snapshot differs from current
    contract_options_snapshot = []
    for snap in ordered_snapshots:
        still_active = (
            snap.contract_duration_uuid is not None
            and snap.contract_duration_uuid in active_uuids
        )
        current = current_duration_by_uuid.get(snap.contract_duration_uuid) if snap.contract_duration_uuid else None
        is_modified = False
        if current and still_active:
            snap_name = (snap.name or "").strip()
            cur_name = (current.name or "").strip()
            if (
                snap_name != cur_name
                or int(snap.duration_months) != int(current.duration_months)
                or float(snap.hardware_fee_percentage) != float(current.hardware_fee_percentage)
                or float(snap.visits_per_contract) != float(current.visits_per_contract)
            ):
                is_modified = True
        contract_options_snapshot.append({
            "name": snap.name,
            "duration_months": snap.duration_months,
            "hardware_fee_percentage": float(snap.hardware_fee_percentage),
            "visits_per_contract": float(snap.visits_per_contract),
            "is_removed": not still_active,
            "is_modified": is_modified,
        })
    # Contract options that exist now but were not in the snapshot (added later); match by UUID only
    contract_options_added = [
        {
            "name": d.name,
            "duration_months": d.duration_months,
            "hardware_fee_percentage": float(d.hardware_fee_percentage),
            "visits_per_contract": float(d.visits_per_contract),
        }
        for d in active_durations_current
        if d.uuid not in snapshot_uuids
    ]
    # Maintenance: use snapshot values if set (frozen in time), else current
    time_per_product = (
        float(proposal.time_per_product_snapshot)
        if proposal.time_per_product_snapshot is not None
        else float(getattr(settings, "time_per_product_minutes", 15) or 15)
    )
    minimum_visit = (
        float(proposal.minimum_visit_snapshot)
        if proposal.minimum_visit_snapshot is not None
        else float(getattr(settings, "minimum_visit_minutes", 60) or 60)
    )
    hourly_rate = (
        float(proposal.hourly_rate_snapshot)
        if proposal.hourly_rate_snapshot is not None
        else float(getattr(settings, "hourly_rate", 75) or 75)
    )
    maintenance_settings = {
        "time_per_product_minutes": time_per_product,
        "minimum_visit_minutes": minimum_visit,
        "hourly_rate": hourly_rate,
        "show_contract_fee_calculation": bool(getattr(settings, "show_contract_fee_calculation", False)),
    }
    context = {
        "proposal": proposal,
        "proposal_lines": data["lines"],
        "grand_total": data["grand_total"],
        "total_value": float(data["total_value"]),
        "total_products": data["total_products"],
        "settings": settings,
        "contract_options_snapshot": contract_options_snapshot,
        "contract_options_added": contract_options_added,
        "maintenance_settings": maintenance_settings,
        "show_contract_fee_calculation": maintenance_settings["show_contract_fee_calculation"],
        "proposal_decimal_sep": settings.decimal_sep() if callable(getattr(settings, "decimal_sep", None)) else ",",
        "proposal_thousands_sep": settings.thousands_sep() if callable(getattr(settings, "thousands_sep", None)) else ".",
        "proposal_calc_i18n": {
            "of_purchase_value": _("of purchase value"),
            "per_visit": _("per visit"),
            "product_s": _("product(s)"),
            "above_minimum": _("Above minimum of {min} min."),
            "below_minimum": _("Below minimum of {min} min, so we use {min} min."),
            "hourly_rate": _("hourly rate"),
            "visits_in_contract_period": _("visits in contract period"),
        },
    }
    inv = get_invoice_for_proposal(proposal)
    has_order = bool(getattr(proposal, "order_id", None))
    order_ok, order_gate_msg = proposal_allows_order_creation(proposal)
    context["invoice"] = inv
    context["has_order"] = has_order
    context["can_create_order_from_proposal"] = order_ok and not has_order
    context["order_gate_message"] = None if order_ok or has_order else order_gate_msg
    return render(request, "pricelist/proposal_detail.html", context)


@require_POST
def proposal_update_rates_view(request, identifier):
    """Update proposal lines to current catalog prices; mark removed products/combinations.
    Also refresh contract snapshots so they have current UUIDs and no false 'added later' labels."""
    proposal = _get_proposal_from_identifier(
        identifier,
        Proposal.objects.prefetch_related(
            Prefetch("lines", queryset=ProposalLine.objects.select_related("product_supplier__supplier"))
        ),
    )
    settings = get_general_settings()
    rounding = getattr(settings, "rounding", "0.01") or "0.01"

    # Refresh contract snapshots to current durations (with UUIDs) so "Contract form added later" is correct
    proposal.contract_snapshots.all().delete()
    for sort_order, duration in enumerate(
        ContractDuration.objects.filter(is_active=True).order_by("duration_months")
    ):
        ProposalContractSnapshot.objects.create(
            proposal=proposal,
            contract_duration=duration,
            contract_duration_uuid=duration.uuid,
            sort_order=sort_order,
            name=duration.name,
            duration_months=duration.duration_months,
            hardware_fee_percentage=duration.hardware_fee_percentage,
            visits_per_contract=duration.visits_per_contract,
        )

    updated = 0
    marked_removed = 0
    for line in proposal.lines.all():
        if line.line_type == ProposalLine.LINE_TYPE_COMBINATION:
            try:
                comb = Combination.objects.get(pk=line.combination_id)
                new_price = comb.offer_price
                if new_price is not None:
                    line.unit_price_snapshot = round_price(new_price, rounding)
                    line.line_total_snapshot = round_price(line.quantity * line.unit_price_snapshot, rounding)
                    line.name_snapshot = comb.name
                    line.is_removed = False
                    line.save(update_fields=["unit_price_snapshot", "line_total_snapshot", "name_snapshot", "is_removed"])
                    updated += 1
            except Combination.DoesNotExist:
                line.is_removed = True
                line.save(update_fields=["is_removed"])
                marked_removed += 1
        else:
            try:
                prod = Product.objects.prefetch_related(
                    Prefetch(
                        "product_suppliers",
                        queryset=ProductSupplier.objects.select_related("supplier").order_by("sort_order", "pk"),
                    )
                ).get(pk=line.product_id)
                ps = line.product_supplier
                if ps is not None and ps.product_id != prod.pk:
                    ps = None
                new_price = prod.sales_price_for_product_supplier(ps) if ps else None
                if new_price is None:
                    new_price = prod.calculated_sales_price
                if new_price is not None:
                    line.unit_price_snapshot = round_price(new_price, rounding)
                    line.line_total_snapshot = round_price(line.quantity * line.unit_price_snapshot, rounding)
                    line.name_snapshot = f"{prod.brand or ''} {prod.model_type or ''}".strip() or prod.name or str(prod)
                    line.is_removed = False
                    if ps and ps.supplier_id:
                        line.supplier_name_snapshot = ps.supplier.name
                    elif prod.supplier_id:
                        line.supplier_name_snapshot = prod.supplier.name
                    line.save(
                        update_fields=[
                            "unit_price_snapshot",
                            "line_total_snapshot",
                            "name_snapshot",
                            "is_removed",
                            "supplier_name_snapshot",
                        ]
                    )
                    updated += 1
            except Product.DoesNotExist:
                line.is_removed = True
                line.save(update_fields=["is_removed"])
                marked_removed += 1
    user = request.user if request.user.is_authenticated else None
    ProposalHistory.objects.create(
        proposal=proposal,
        action=ProposalHistory.ACTION_UPDATED_RATES,
        description=_("Prices updated to current rates. %(updated)d lines updated, %(removed)d marked as no longer in catalog.") % {"updated": updated, "removed": marked_removed},
        user=user,
        details={"updated": updated, "marked_removed": marked_removed},
    )
    return redirect("pricelist:proposal_detail", identifier=proposal.uuid)


def proposal_history_view(request, identifier):
    """Show history of a saved proposal (identifier = UUID or reference)."""
    proposal = _get_proposal_from_identifier(
        identifier,
        Proposal.objects.prefetch_related("history_entries"),
    )
    entries = proposal.history_entries.all()[:100]
    context = {"proposal": proposal, "entries": entries}
    return render(request, "pricelist/proposal_history.html", context)


# ----- Orders (from saved proposals) -----
# Orders are created from a saved proposal. Each order has OrderLines (one per proposal line) and
# OrderLineItems (one per product or per combination item) so we can track ordered/expected/delivered per item.


def order_list_view(request):
    """List all orders (like saved calculations list)."""
    orders = (
        Order.objects.select_related("proposal", "created_by", "invoice")
        .prefetch_related("lines")
        .order_by("-created_at")[:200]
    )
    settings = get_general_settings()
    context = {"orders": orders, "settings": settings}
    return render(request, "pricelist/order_list.html", context)


@require_http_methods(["GET", "POST"])
def order_create_view(request, identifier):
    """
    Create an order from a saved proposal. One OrderLine per proposal line; for each line we create
    OrderLineItems: one per product (combination_item=None) or one per combination item, so the
    order detail page can show and save ordered/expected/delivered per item.
    """
    proposal = _get_proposal_from_identifier(
        identifier,
        Proposal.objects.prefetch_related(
            Prefetch("lines", queryset=ProposalLine.objects.select_related("product_supplier__supplier"))
        ),
    )
    ok, err_msg = proposal_allows_order_creation(proposal)
    if not ok:
        messages.error(request, err_msg)
        return redirect("pricelist:proposal_detail", identifier=proposal.uuid)
    inv = get_invoice_for_proposal(proposal)
    user = request.user if request.user.is_authenticated else None
    order = create_order_from_proposal(proposal, user, invoice=inv)
    # Use UUID for stable external links; legacy int-PK route still exists.
    return redirect("pricelist:order_detail_uuid", pk=order.uuid)


def _order_supplier_groups(order):
    """
    Group order line items by supplier for the order detail table. Each row is one OrderLineItem so
    the user can set ordered_at, expected_delivery, delivered_at per product (and per item in a combination).
    Returns a list of dicts: {supplier_name, rows} where each row has order_line_item, label, quantity, etc.
    """
    return build_supplier_groups(order)


@require_http_methods(["GET", "POST"])
def order_detail_view(request, pk):
    """
    Order detail: per-supplier table of order line items. User can set order status, order note,
    and per-item ordered_at / expected_delivery / delivered_at (form fields named oli_<id>_ordered, etc.).
    """
    order_qs = Order.objects.select_related(
        "proposal",
        "invoice",
        "proposal__client_crm_organization",
        "proposal__client_crm_department",
        "proposal__client_crm_contact__person",
    ).prefetch_related("lines__proposal_line")
    order = order_qs.filter(pk=pk).first()
    if order is None:
        # UUID-based route passes a UUID into `pk` URL kwarg.
        order = order_qs.filter(uuid=pk).first()
    if order is None:
        raise Http404(_("No order found."))
    settings = get_general_settings()
    if request.method == "POST":
        try:
            with transaction.atomic():
                update_order_from_post(order, request.POST)
        except ValidationError as exc:
            parts: list[str] = []
            if getattr(exc, "error_dict", None):
                for errs in exc.error_dict.values():
                    parts.extend(str(e) for e in errs)
            elif getattr(exc, "error_list", None):
                parts.extend(str(e) for e in exc.error_list)
            elif getattr(exc, "messages", None):
                parts.extend(str(m) for m in exc.messages)
            messages.error(
                request,
                " ".join(parts) if parts else str(exc),
            )
        return redirect("pricelist:order_detail_uuid", pk=order.uuid)
    supplier_groups = _order_supplier_groups(order)
    org = order.proposal.client_crm_organization
    order_client_crm_picker = single_organization_client_picker_payload(org) if org else None
    context = {
        "order": order,
        "proposal": order.proposal,
        "supplier_groups": supplier_groups,
        "settings": settings,
        "order_status_choices": Order.STATUS_CHOICES,
        "order_client_crm_picker": order_client_crm_picker,
    }
    return render(request, "pricelist/order_detail.html", context)
