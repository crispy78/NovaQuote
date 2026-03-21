from decimal import Decimal

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import (
    Category,
    Combination,
    CombinationItem,
    ContractDuration,
    Department,
    FrontendRole,
    GeneralSettings,
    Invoice,
    InvoicePayment,
    Organization,
    OrganizationInvoice,
    OrganizationNetworkLink,
    OrganizationPerson,
    OrganizationRole,
    OrganizationShipment,
    PriceHistory,
    Person,
    PersonEvent,
    PersonHobby,
    PersonLifeEvent,
    Product,
    ProductSupplier,
    Proposal,
    ProposalContractSnapshot,
    ProposalHistory,
    ProposalLine,
    ProductOption,
    ProfitProfile,
    Supplier,
    UserFrontendProfile,
    format_number_with_separators,
    get_general_settings,
    price_decimal_places,
    round_price,
)


def _disable_fk_add_related(formfield):
    """
    Hide the admin (+) “add related” control on a ModelChoiceField.

    Must run after BaseModelAdmin.formfield_for_dbfield wraps the widget in
    RelatedFieldWidgetWrapper; setting this in formfield_for_foreignkey is too early.
    """
    widget = getattr(formfield, "widget", None)
    if widget is not None and hasattr(widget, "can_add_related"):
        widget.can_add_related = False


class CatalogRemovedFilter(admin.SimpleListFilter):
    """Filter catalog rows that are soft-deleted (hidden from the price list)."""

    title = _("Removed from catalog")
    parameter_name = "catalog_removed"

    def lookups(self, request, model_admin):
        return [
            ("no", _("Active")),
            ("yes", _("Removed (hidden)")),
        ]

    def queryset(self, request, queryset):
        v = self.value()
        if v == "yes":
            return queryset.filter(deleted_at__isnull=False)
        if v == "no":
            return queryset.filter(deleted_at__isnull=True)
        return queryset


def _format_sales_price_admin(value):
    """Format sales price for display in admin (dropdown/list)."""
    if value is None:
        return ""
    settings = get_general_settings()
    rounding = getattr(settings, "rounding", None) or "0.01"
    r = round_price(value, rounding)
    if r is None:
        return ""
    dec = price_decimal_places(rounding)
    decimal_sep = settings.decimal_sep() if callable(getattr(settings, "decimal_sep", None)) else ","
    thousands_sep = settings.thousands_sep() if callable(getattr(settings, "thousands_sep", None)) else "."
    formatted = format_number_with_separators(r, dec, decimal_sep, thousands_sep)
    currency = (getattr(settings, "currency", None) or "EUR").strip()
    return f"{currency} {formatted}".strip()


@admin.register(ContractDuration)
class ContractDurationAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_months", "hardware_fee_percentage", "visits_per_contract", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    ordering = ("duration_months",)
    search_fields = ("name",)


class ProposalLineInline(admin.TabularInline):
    model = ProposalLine
    extra = 0
    readonly_fields = (
        "line_type",
        "product",
        "combination",
        "product_supplier",
        "supplier_name_snapshot",
        "unit_price_snapshot",
        "line_total_snapshot",
        "name_snapshot",
        "is_removed",
    )
    can_delete = True
    fields = (
        "sort_order",
        "line_type",
        "product",
        "combination",
        "product_supplier",
        "supplier_name_snapshot",
        "quantity",
        "unit_price_snapshot",
        "line_total_snapshot",
        "name_snapshot",
        "is_removed",
    )
    ordering = ("sort_order", "id")


class ProposalContractSnapshotInline(admin.TabularInline):
    model = ProposalContractSnapshot
    extra = 0
    ordering = ("sort_order", "id")


class ProposalAdminForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client_org_pks = Organization.objects.filter(
            role_assignments__role__in=[OrganizationRole.ROLE_CLIENT, OrganizationRole.ROLE_LEAD]
        ).values_list("pk", flat=True)
        client_org_pks = list(dict.fromkeys(client_org_pks))
        self.fields["client_crm_organization"].queryset = Organization.objects.filter(pk__in=client_org_pks).order_by(
            "name"
        )
        self.fields["client_crm_department"].queryset = (
            Department.objects.filter(organization_id__in=client_org_pks)
            .select_related("organization")
            .order_by("organization__name", "name")
        )
        self.fields["client_crm_contact"].queryset = (
            OrganizationPerson.objects.filter(organization_id__in=client_org_pks)
            .select_related("person", "organization")
            .order_by("organization__name", "person__last_name", "person__first_name")
        )
        for fn in ("client_crm_organization", "client_crm_department", "client_crm_contact"):
            self.fields[fn].required = False


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    form = ProposalAdminForm
    list_display = ("id", "uuid", "reference", "created_at", "updated_at", "created_by")
    list_filter = ("created_at",)
    search_fields = ("reference", "uuid")
    readonly_fields = ("uuid", "created_at", "updated_at", "time_per_product_snapshot", "minimum_visit_snapshot", "hourly_rate_snapshot")
    autocomplete_fields = (
        "client_crm_organization",
        "client_crm_department",
        "client_crm_contact",
    )
    inlines = [ProposalLineInline, ProposalContractSnapshotInline]


@admin.register(ProposalHistory)
class ProposalHistoryAdmin(admin.ModelAdmin):
    list_display = ("proposal", "action", "at", "user")
    list_filter = ("action", "at")
    readonly_fields = ("proposal", "at", "action", "description", "user", "details")


@admin.register(GeneralSettings)
class GeneralSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "currency",
        "rounding",
        "number_format",
        "color_scheme",
        "minimum_margin_percentage",
        "show_price_history_chart_on_product_page",
        "show_cost_in_price_history_chart",
        "show_sales_in_price_history_chart",
        "show_supplier_on_frontend",
        "show_category_on_frontend",
        "language",
    )
    fieldsets = [
        (_("Branding"), {
            "fields": ("site_name", "logo", "color_scheme"),
            "description": _(
                "Logo: leave empty for the default NovaQuote mark, or upload your own. "
                "Choose NovaQuote logo (default), Orange, Navy blue, Teal, Black, or Red for the theme; primary and hover hex values are set automatically."
            ),
            "classes": ("tc-fieldset-group",),
        }),
        (_("Currency and number format"), {
            "fields": ("currency", "rounding", "number_format", "minimum_margin_percentage"),
            "description": _("Currency and rounding apply to the price list, product pages and proposals. Minimum margin percent is used for combinations (0 = no check)."),
            "classes": ("tc-fieldset-group",),
        }),
        (_("Price list and product page display"), {
            "fields": (
                "show_price_history_chart_on_product_page",
                "show_cost_in_price_history_chart",
                "show_sales_in_price_history_chart",
                "show_supplier_on_frontend",
                "show_category_on_frontend",
            ),
            "description": _("What to show on the public price list and product detail pages."),
            "classes": ("tc-fieldset-group",),
        }),
        (_("Language"), {
            "fields": ("language",),
            "description": _("Language for the price list and proposal pages. The admin interface keeps the browser or system language."),
            "classes": ("tc-fieldset-group",),
        }),
        (_("Maintenance contract calculation"), {
            "fields": (
                "time_per_product_minutes",
                "minimum_visit_minutes",
                "hourly_rate",
                "show_contract_fee_calculation",
            ),
            "description": _("Used on the proposal page for maintenance contract options. Time in minutes; hourly rate in your currency. Visits per contract are set per contract duration. Enable the fee calculation option to show the breakdown under each contract option."),
            "classes": ("tc-fieldset-group",),
        }),
    ]

    def has_add_permission(self, request):
        return not GeneralSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Ensure one record exists (create if needed), then redirect to change form
        from .models import get_general_settings
        obj = get_general_settings()
        return HttpResponseRedirect(
            reverse("admin:pricelist_generalsettings_change", args=[obj.pk])
        )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "contact_person", "email")
    search_fields = ("name", "contact_person", "email")
    readonly_fields = ("uuid",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser and "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "sort_order")
    ordering = ("sort_order", "name")
    search_fields = ("name",)
    readonly_fields = ("uuid",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser and "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(ProfitProfile)
class ProfitProfileAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "markup_percentage", "markup_fixed", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("uuid",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser and "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

class PriceHistoryInline(admin.TabularInline):
    model = PriceHistory
    extra = 0
    can_delete = False
    readonly_fields = ("previous_cost_price", "new_cost_price", "sales_price_at_date", "change_date")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ProductSupplierInline(admin.TabularInline):
    model = ProductSupplier
    fk_name = "product"
    extra = 0
    # Use a normal dropdown (not autocomplete): autocomplete is type-to-search and often breaks
    # in admin popups; suppliers are typically a small list.
    ordering = ("sort_order", "supplier__name")
    fields = (
        "supplier",
        "cost_price",
        "supplier_order_number",
        "lead_time_days",
        "payment_terms",
        "payment_terms_days",
        "is_preferred",
        "sort_order",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "supplier":
            kwargs["queryset"] = Supplier.objects.all().order_by("name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if (
            isinstance(db_field, models.ForeignKey)
            and db_field.name == "supplier"
            and formfield is not None
        ):
            _disable_fk_add_related(formfield)
        return formfield


class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    fk_name = "main_product"
    extra = 0
    autocomplete_fields = ("option_product",)
    ordering = ("sort_order",)


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"
        exclude = ("name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        supplier_org_pks = Organization.objects.filter(
            role_assignments__role=OrganizationRole.ROLE_SUPPLIER
        ).values_list("pk", flat=True)
        supplier_org_pks = list(dict.fromkeys(supplier_org_pks))
        self.fields["supplier_crm_organization"].queryset = Organization.objects.filter(pk__in=supplier_org_pks).order_by(
            "name"
        )
        self.fields["supplier_crm_department"].queryset = (
            Department.objects.filter(organization_id__in=supplier_org_pks)
            .select_related("organization")
            .order_by("organization__name", "name")
        )
        self.fields["supplier_crm_contact"].queryset = (
            OrganizationPerson.objects.filter(organization_id__in=supplier_org_pks)
            .select_related("person", "organization")
            .order_by("organization__name", "person__last_name", "person__first_name")
        )
        self.fields["supplier_crm_organization"].required = False
        self.fields["supplier_crm_department"].required = False
        self.fields["supplier_crm_contact"].required = False

    def clean_profit_profile(self):
        profit_profile = self.cleaned_data.get("profit_profile")
        if not profit_profile:
            raise forms.ValidationError(_("Select a profit profile for this product."))
        if not profit_profile.is_active:
            raise forms.ValidationError(_("The selected profit profile is inactive. Choose an active profit profile."))
        return profit_profile


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "brand",
        "model_type",
        "article_number",
        "catalog_removed_badge",
        "show_in_price_list",
        "is_margin_product",
        "cost_price",
        "fixed_sales_price",
        "calculated_sales_price_two_decimals",
        "price_last_changed",
        "price_last_checked",
    )
    list_editable = ("show_in_price_list", "is_margin_product")
    list_filter = ("supplier", "category", "profit_profile", "show_in_price_list", CatalogRemovedFilter)
    search_fields = ("brand", "model_type", "supplier_order_number", "description", "supplier__name")
    readonly_fields = ("price_last_changed", "article_number")
    autocomplete_fields = (
        "supplier_crm_organization",
        "supplier_crm_department",
        "supplier_crm_contact",
    )
    inlines = [ProductSupplierInline, PriceHistoryInline, ProductOptionInline]
    form = ProductAdminForm

    class Media:
        js = ("pricelist/admin/product_supplier_cost_sync.js",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if (
            isinstance(db_field, models.ForeignKey)
            and db_field.name == "supplier"
            and formfield is not None
        ):
            _disable_fk_add_related(formfield)
        return formfield

    @admin.display(description=_("Calculated sales price"))
    def calculated_sales_price_two_decimals(self, obj):
        if obj is None or obj.calculated_sales_price is None:
            return ""
        return f"{float(obj.calculated_sales_price):.2f}"

    @admin.display(description=_("Removed"), boolean=True)
    def catalog_removed_badge(self, obj):
        return obj.deleted_at is not None

    def get_queryset(self, request):
        return Product.all_objects.select_related("supplier", "category", "profit_profile").order_by(
            "brand", "model_type", "pk"
        )

    def has_delete_permission(self, request, obj=None):
        """Hard delete disabled; use frontend catalog trash (superuser: purge)."""
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class CombinationItemForm(forms.ModelForm):
    """Restrict product to price-list products; selected options to options of that product."""

    class Meta:
        model = CombinationItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only products that appear on the price list (so e.g. Display/Cutter can only be options for Lemur-C)
        self.fields["product"].queryset = Product.objects.filter(show_in_price_list=True).order_by(
            "brand", "model_type"
        )
        product_id = getattr(self.instance, "product_id", None) if self.instance else None
        if product_id is None and self.data and self.prefix:
            raw = self.data.get(self.prefix + "-product")
            if raw:
                try:
                    product_id = int(raw)
                except (TypeError, ValueError):
                    pass
        if product_id:
            # Only products that are options for this product (ProductOption)
            option_pks = list(
                ProductOption.objects.filter(main_product_id=product_id).values_list(
                    "option_product_id", flat=True
                )
            )
            if option_pks:
                self.fields["selected_options"].queryset = (
                    Product.objects.filter(pk__in=option_pks)
                    .select_related("profit_profile")
                    .order_by("brand", "model_type")
                )
                self.fields["selected_options"].help_text = _(
                    "Only the options that belong to this product."
                )
            else:
                self.fields["selected_options"].queryset = Product.objects.none()
                self.fields["selected_options"].help_text = (
                    "This product has no options. Configure options on the product page (Catalog → Products)."
                )
        else:
            self.fields["selected_options"].queryset = Product.objects.none()
            self.fields["selected_options"].help_text = (
                "Choose a product first. Then only the options for that product will appear here."
            )
        # Don't replace the widget here: the widget from formfield_for_manytomany shares the field's
        # choices; a new CheckboxSelectMultiple() would have no choices and render empty.
        def product_label(p):
            label = f"{p.brand or ''} {p.model_type or ''}".strip() or str(p.article_number)
            price = _format_sales_price_admin(p.calculated_sales_price)
            return f"{label} — {price}" if price else label

        self.fields["product"].label_from_instance = product_label


class CombinationItemInline(admin.TabularInline):
    model = CombinationItem
    form = CombinationItemForm
    extra = 0
    fields = ("product", "sales_price_display", "sort_order", "selected_options")
    readonly_fields = ("sales_price_display",)
    # Don't use filter_horizontal here: FilteredSelectMultiple is too wide for a table cell and
    # breaks the layout (delete column wraps). Use checkboxes so options are selectable per row.
    ordering = ("sort_order",)
    verbose_name = _("Combination item")
    verbose_name_plural = _("Combination items (product + selected options)")
    description = _(
        "Choose the main product and optionally the options for that product. "
        "Products without options (e.g. Newland HR33) show no option choice. "
        "Delete only removes the product from this combination, not from the catalog."
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "product__profit_profile")

    @admin.display(description=_("Sales price"))
    def sales_price_display(self, obj):
        if obj and obj.product_id:
            return _format_sales_price_admin(obj.product.calculated_sales_price)
        return "—"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "product":
            if hasattr(formfield.widget, "can_add_related"):
                formfield.widget.can_add_related = False
            if hasattr(formfield.widget, "can_change_related"):
                formfield.widget.can_change_related = False
        return formfield

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "selected_options":
            # Compact widget for tabular inline: checkboxes are selectable and don't push Delete column away
            formfield.widget = forms.CheckboxSelectMultiple()
        return formfield


class CombinationForm(forms.ModelForm):
    """Form for Combination: show only discount amount/percentage; map none/fixed to discount amount."""

    class Meta:
        model = Combination
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.offer_type in (
                Combination.OFFER_TYPE_NONE,
                Combination.OFFER_TYPE_FIXED_AMOUNT,
            ):
                self.initial = dict(self.initial) if self.initial else {}
                self.initial["offer_type"] = Combination.OFFER_TYPE_DISCOUNT_AMOUNT


@admin.register(Combination)
class CombinationAdmin(admin.ModelAdmin):
    form = CombinationForm
    change_form_template = "admin/pricelist/combination/change_form.html"
    list_display = (
        "uuid",
        "name",
        "catalog_removed_badge",
        "original_price",
        "offer_price_admin",
        "margin_admin",
        "date_range",
    )
    list_filter = (CatalogRemovedFilter,)
    inlines = [CombinationItemInline]
    readonly_fields = ("uuid", "margin_preview_placeholder",)

    fieldsets = [
        (None, {"fields": ("name", "description", "image", "usps")}),
        (
            _("Price and margin"),
            {
                "fields": (
                    "offer_type",
                    "discount_amount",
                    "discount_percentage",
                    "margin_preview_placeholder",
                ),
                "description": _("Left: offer and discount (for margin products only). Right: live margin overview."),
                "classes": ("price-margin-two-columns",),
            },
        ),
    ]

    class Media:
        css = {"all": ("pricelist/combination_admin.css",)}
        js = ("pricelist/combination_marge.js", "pricelist/combination_item_options_visibility.js",)

    def _combination_extra_context(self, extra_context=None):
        extra_context = extra_context or {}
        # Product IDs that have at least one option (for JS: show option fields only then)
        extra_context["product_ids_with_options"] = list(
            ProductOption.objects.values_list("main_product_id", flat=True).distinct()
        )
        product_options_map = {}
        for po in (
            ProductOption.objects.select_related("option_product")
            .order_by("main_product_id", "sort_order")
        ):
            pid = po.main_product_id
            if pid not in product_options_map:
                product_options_map[pid] = []
            label = po.short_description.strip() or str(po.option_product)
            product_options_map[pid].append({"id": po.option_product_id, "label": label})
        extra_context["product_options_map"] = product_options_map
        from_product_ids = set(
            Product.objects.filter(show_in_price_list=True).values_list("pk", flat=True)
        )
        option_product_ids = set(
            ProductOption.objects.values_list("option_product_id", flat=True)
        )
        all_ids = from_product_ids | option_product_ids
        product_prices = {}
        for p in Product.objects.filter(pk__in=all_ids).select_related("profit_profile"):
            sales = p.calculated_sales_price
            cost = Decimal("0") if p.fixed_sales_price is not None else (p.cost_price or Decimal("0"))
            product_prices[str(p.pk)] = {
                "sales": str(sales if sales is not None else 0),
                "cost": str(cost),
                "margin_product": getattr(p, "is_margin_product", True),
            }
        extra_context["product_prices"] = product_prices
        # Labels for the live margin table (JS), translatable; keys in English for JS
        extra_context["combination_margin_labels"] = {
            "label_col": _("Item"),
            "margin_products": _("Margin products"),
            "other_revenue": _("Other revenue"),
            "other_revenue_not_discountable": _("Other revenue (not discountable)"),
            "total": _("Total"),
            "subtotal": _("Subtotal"),
            "margin": _("Margin"),
            "discount": _("Discount (fixed amount or %)"),
            "margin_after_discount": _("Margin after discount"),
            "selling_price": _("Selling price"),
            "info": _("Info"),
            "below_minimum_margin": _("Below minimum margin ({min}%)"),
        }
        return extra_context

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(
            request, object_id, form_url, extra_context=self._combination_extra_context(extra_context)
        )

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(
            request, form_url, extra_context=self._combination_extra_context(extra_context)
        )

    @admin.display(description="")
    def margin_preview_placeholder(self, obj):
        # Content is filled entirely by JavaScript from the current form fields.
        return mark_safe('<div id="live-margin-info" class="help"></div>')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Show only discount amount and discount percentage; label "Discount"
        form.base_fields["offer_type"].label = _("Discount")
        form.base_fields["offer_type"].choices = [
            (Combination.OFFER_TYPE_DISCOUNT_AMOUNT, _("Discount amount")),
            (Combination.OFFER_TYPE_DISCOUNT_PERCENTAGE, _("Discount percentage")),
        ]
        form.base_fields["discount_amount"].label = _("Discount amount")
        form.base_fields["discount_percentage"].label = _("Discount percentage")
        if obj is not None:
            cost = getattr(obj, "total_cost_price", None) or Decimal("0.00")
            orig = getattr(obj, "original_price", None) or Decimal("0.00")
            inst = get_general_settings()
            min_margin = getattr(inst, "minimum_margin_percentage", None) or Decimal("0.00")
            data_attrs = {
                "data-cost": str(cost),
                "data-original": str(orig),
                "data-min-margin": str(min_margin),
                "data-currency": (getattr(inst, "currency", None) or "EUR").strip(),
            }
            for field_name in (
                "offer_type",
                "discount_amount",
                "discount_percentage",
            ):
                if field_name in form.base_fields:
                    form.base_fields[field_name].widget.attrs.update(data_attrs)
        return form

    def save_model(self, request, obj, form, change):
        """Ensure combination_sales_price is never NULL (DB constraint). Value is set in save_related after items are saved."""
        if obj.combination_sales_price is None:
            obj.combination_sales_price = Decimal("0.00")
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """After saving inline items: set combination_sales_price to the calculated offer price."""
        super().save_related(request, form, formsets, change)
        combination = form.instance
        combination.refresh_from_db()
        combination.combination_sales_price = combination.offer_price
        combination.save(update_fields=["combination_sales_price"])

    @admin.display(description=_("Offer price"))
    def offer_price_admin(self, obj: Combination):
        inst = get_general_settings()
        rounding = getattr(inst, "rounding", "0.01") or "0.01"
        val = obj.offer_price
        if val is None:
            return "-"
        rounded = round_price(val, rounding)
        dec = price_decimal_places(rounding)
        if dec == 0:
            formatted = f"{int(rounded)}"
        else:
            formatted = f"{rounded:.{dec}f}"
        return f"{getattr(inst, 'currency', 'EUR')} {formatted}"

    @admin.display(description=_("Margin"), ordering="id")
    def margin_admin(self, obj: Combination):
        margin = obj.margin_percentage
        if margin is None:
            return "-"
        text = f"{margin:.1f}%"
        if obj.margin_below_minimum:
            return format_html('<span style="color:#b91c1c; font-weight:600;">{} ⚠</span>', text)
        return text

    @admin.display(description=_("Removed"), boolean=True)
    def catalog_removed_badge(self, obj):
        return obj.deleted_at is not None

    def get_queryset(self, request):
        return Combination.all_objects.order_by("name")

    def has_delete_permission(self, request, obj=None):
        """Hard delete disabled; use frontend catalog trash (superuser: purge)."""
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        # No bulk delete: prevents accidentally removing the whole combination instead of just items.
        # Delete only via the edit page (red Delete button).
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "previous_cost_price", "new_cost_price", "sales_price_at_date", "change_date")
    readonly_fields = ("product", "previous_cost_price", "new_cost_price", "sales_price_at_date", "change_date")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --- Contacts (CRM) -----------------------------------------------------------------


class OrganizationRoleInline(admin.TabularInline):
    model = OrganizationRole
    extra = 0
    readonly_fields = ("uuid",)


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0
    readonly_fields = ("uuid",)


class OrganizationPersonInline(admin.TabularInline):
    model = OrganizationPerson
    fk_name = "organization"
    extra = 0
    readonly_fields = ("uuid",)
    autocomplete_fields = ("person", "department")


class OrganizationInvoiceInline(admin.TabularInline):
    model = OrganizationInvoice
    extra = 0
    readonly_fields = ("uuid", "created_at")


class OrganizationShipmentInline(admin.TabularInline):
    model = OrganizationShipment
    extra = 0
    readonly_fields = ("uuid", "created_at")


class OrganizationNetworkLinkOutInline(admin.TabularInline):
    """Links where this org is the network partner (outbound)."""

    model = OrganizationNetworkLink
    fk_name = "network_organization"
    extra = 0
    readonly_fields = ("uuid", "created_at")
    autocomplete_fields = ("linked_organization",)


class OrganizationNetworkLinkInInline(admin.TabularInline):
    """Links where this org is the supplier/client/lead side (inbound)."""

    model = OrganizationNetworkLink
    fk_name = "linked_organization"
    extra = 0
    readonly_fields = ("uuid", "created_at")
    autocomplete_fields = ("network_organization",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "legal_name",
        "email",
        "phone",
        "lead_pipeline_status",
        "client_promotion_override",
        "created_at",
    )
    list_filter = ("lead_pipeline_status", "client_promotion_override")
    search_fields = ("name", "legal_name", "email", "vat_number", "coc_number", "uuid")
    readonly_fields = ("uuid", "client_since", "created_at", "updated_at")
    inlines = [
        OrganizationRoleInline,
        DepartmentInline,
        OrganizationPersonInline,
        OrganizationNetworkLinkOutInline,
        OrganizationNetworkLinkInInline,
        OrganizationInvoiceInline,
        OrganizationShipmentInline,
    ]


class OrganizationPersonFromPersonInline(admin.TabularInline):
    model = OrganizationPerson
    fk_name = "person"
    extra = 0
    readonly_fields = ("uuid",)
    autocomplete_fields = ("organization", "department")


class PersonHobbyInline(admin.TabularInline):
    model = PersonHobby
    extra = 0
    readonly_fields = ("uuid",)
    ordering = ("sort_order", "name")


class PersonEventInline(admin.TabularInline):
    model = PersonEvent
    extra = 0
    readonly_fields = ("uuid",)


class PersonLifeEventInline(admin.TabularInline):
    model = PersonLifeEvent
    extra = 0
    readonly_fields = ("uuid",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "personal_email", "personal_mobile")
    search_fields = ("first_name", "last_name", "personal_email", "uuid")
    readonly_fields = ("uuid", "created_at", "updated_at")
    inlines = [
        OrganizationPersonFromPersonInline,
        PersonHobbyInline,
        PersonEventInline,
        PersonLifeEventInline,
    ]


@admin.register(PersonHobby)
class PersonHobbyAdmin(admin.ModelAdmin):
    list_display = ("name", "person", "sort_order")
    search_fields = ("name", "person__first_name", "person__last_name", "uuid")
    readonly_fields = ("uuid",)
    autocomplete_fields = ("person",)


@admin.register(PersonEvent)
class PersonEventAdmin(admin.ModelAdmin):
    list_display = ("name", "event_date", "reminder", "person")
    list_filter = ("reminder",)
    search_fields = ("name", "person__first_name", "person__last_name", "uuid")
    readonly_fields = ("uuid",)
    autocomplete_fields = ("person",)


@admin.register(PersonLifeEvent)
class PersonLifeEventAdmin(admin.ModelAdmin):
    list_display = ("person", "occurred_on", "note_preview")
    search_fields = ("note", "person__first_name", "person__last_name")
    readonly_fields = ("uuid",)
    autocomplete_fields = ("person",)

    @admin.display(description=_("Note"))
    def note_preview(self, obj):
        n = obj.note or ""
        text = n[:80]
        return text + ("…" if len(n) > 80 else "")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "email", "phone")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name")
    readonly_fields = ("uuid",)
    autocomplete_fields = ("organization",)


@admin.register(OrganizationPerson)
class OrganizationPersonAdmin(admin.ModelAdmin):
    list_display = ("person", "organization", "department", "job_title", "is_primary_contact")
    list_filter = ("is_primary_contact", "organization")
    search_fields = ("person__first_name", "person__last_name", "organization__name", "job_title", "company_email")
    readonly_fields = ("uuid",)
    autocomplete_fields = ("person", "organization", "department")


@admin.register(OrganizationInvoice)
class OrganizationInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "organization", "issued_on", "amount", "created_at")
    search_fields = ("invoice_number", "organization__name")
    readonly_fields = ("uuid", "created_at")
    autocomplete_fields = ("organization",)
    date_hierarchy = "issued_on"


@admin.register(OrganizationShipment)
class OrganizationShipmentAdmin(admin.ModelAdmin):
    list_display = ("reference", "organization", "shipped_on", "created_at")
    search_fields = ("reference", "organization__name")
    readonly_fields = ("uuid", "created_at")
    autocomplete_fields = ("organization",)
    date_hierarchy = "shipped_on"


@admin.register(OrganizationNetworkLink)
class OrganizationNetworkLinkAdmin(admin.ModelAdmin):
    list_display = ("network_organization", "linked_organization", "created_at")
    search_fields = (
        "network_organization__name",
        "linked_organization__name",
        "notes",
        "uuid",
    )
    readonly_fields = ("uuid", "created_at")
    autocomplete_fields = ("network_organization", "linked_organization")


@admin.register(OrganizationRole)
class OrganizationRoleAdmin(admin.ModelAdmin):
    list_display = ("organization", "role")
    list_filter = ("role",)
    search_fields = ("organization__name",)
    readonly_fields = ("uuid",)
    autocomplete_fields = ("organization",)


@admin.register(FrontendRole)
class FrontendRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order")
    ordering = ("sort_order", "name")
    search_fields = ("name", "slug", "description")
    readonly_fields = ("uuid",)
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "sort_order", "uuid")}),
        (
            _("Price list and catalog"),
            {
                "fields": (
                    "access_price_list",
                    "access_catalog",
                    "catalog_change",
                    "catalog_soft_delete",
                    "catalog_trash",
                    "catalog_purge",
                ),
            },
        ),
        (
            _("Sales workflow"),
            {"fields": ("access_proposals", "access_invoicing", "access_orders")},
        ),
        (_("Contacts"), {"fields": ("access_contacts", "contacts_write")}),
    )


@admin.register(UserFrontendProfile)
class UserFrontendProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "role")
    readonly_fields = ("uuid",)


class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    readonly_fields = ("uuid", "created_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "status",
        "proposal",
        "grand_total_snapshot",
        "issued_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("invoice_number", "proposal__reference", "proposal__uuid", "uuid")
    readonly_fields = ("uuid", "created_at", "updated_at")
    # Autocomplete shows Proposal.__str__ (reference + UUID), not the raw integer PK.
    autocomplete_fields = ("proposal",)
    inlines = (InvoicePaymentInline,)

