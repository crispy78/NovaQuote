"""
Forms for frontend catalog management (products & combinations).
"""

from __future__ import annotations

from django import forms


def _style_form_widgets(fields: dict) -> None:
    base = "w-full max-w-xl border border-slate-300 rounded-lg px-3 py-2 text-slate-900"
    for field in fields.values():
        w = field.widget
        if isinstance(w, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.URLInput)):
            w.attrs.setdefault("class", base)
        elif isinstance(w, forms.Textarea):
            w.attrs.setdefault("class", base)
        elif isinstance(w, forms.Select):
            w.attrs.setdefault("class", base + " bg-white")
        elif isinstance(w, forms.ClearableFileInput):
            w.attrs.setdefault("class", "block text-sm text-slate-600")
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from django.db.models import Prefetch

from .models import (
    Category,
    Combination,
    CombinationItem,
    Department,
    Organization,
    OrganizationPerson,
    OrganizationRole,
    Product,
    ProductOption,
    ProductSupplier,
    ProfitProfile,
    Supplier,
)

class CatalogProductForm(forms.ModelForm):
    """Product editor for the catalog menu (mirrors key admin fields)."""

    class Meta:
        model = Product
        fields = [
            "brand",
            "model_type",
            "description",
            "usps",
            "category",
            "image",
            "fixed_sales_price",
            "profit_profile",
            "show_in_price_list",
            "is_margin_product",
            "supplier_crm_organization",
            "supplier_crm_department",
            "supplier_crm_contact",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("sort_order", "name")
        self.fields["profit_profile"].queryset = ProfitProfile.objects.order_by("name")
        self.fields["description"].widget.attrs.setdefault("rows", 4)
        self.fields["usps"].widget.attrs.setdefault("rows", 3)
        cb_attrs = (
            "rounded border-slate-300 text-[var(--brand)] focus:ring-[var(--brand)] shrink-0 mt-1 h-4 w-4"
        )
        self.fields["show_in_price_list"].widget.attrs.setdefault("class", cb_attrs)
        self.fields["is_margin_product"].widget.attrs.setdefault("class", cb_attrs)
        supplier_org_pks = list(
            Organization.objects.filter(role_assignments__role=OrganizationRole.ROLE_SUPPLIER)
            .values_list("pk", flat=True)
            .distinct()
        )
        self.fields["supplier_crm_organization"].queryset = Organization.objects.filter(
            pk__in=supplier_org_pks
        ).order_by("name")
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
        for fname in ("supplier_crm_organization", "supplier_crm_department", "supplier_crm_contact"):
            self.fields[fname].required = False
        self.fields["supplier_crm_organization"].help_text = _(
            "Optional. Link a Contacts organization that has the supplier role (for CRM). The suppliers you purchase from are listed in the table above."
        )
        self.fields["supplier_crm_department"].help_text = _(
            "Optional. Department at the selected supplier company."
        )
        self.fields["supplier_crm_contact"].help_text = _(
            "Optional. Default contact at that company."
        )
        _style_form_widgets(self.fields)

    def clean_profit_profile(self):
        profile = self.cleaned_data.get("profit_profile")
        if not profile:
            raise forms.ValidationError(_("Select a profit profile for this product."))
        if not profile.is_active:
            raise forms.ValidationError(_("The selected profit profile is inactive."))
        return profile


class CatalogProductSupplierOfferForm(forms.ModelForm):
    """One catalog supplier row: own cost and supplier article / order number."""

    class Meta:
        model = ProductSupplier
        fields = [
            "supplier",
            "cost_price",
            "supplier_order_number",
            "is_preferred",
            "sort_order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.order_by("name")
        self.fields["supplier_order_number"].widget.attrs.setdefault(
            "placeholder", _("Supplier’s SKU / article / order code")
        )
        pref = (
            "catalog-supplier-preferred rounded border-slate-300 text-[var(--brand)] "
            "focus:ring-[var(--brand)] shrink-0 h-4 w-4"
        )
        self.fields["is_preferred"].widget.attrs.setdefault("class", pref)
        narrow = "w-full max-w-[5rem] border border-slate-300 rounded-lg px-2 py-1.5 text-slate-900"
        self.fields["sort_order"].widget.attrs.setdefault("class", narrow)
        self.fields["cost_price"].widget.attrs.setdefault(
            "class", "w-full max-w-[8rem] border border-slate-300 rounded-lg px-2 py-1.5 text-slate-900"
        )
        self.fields["supplier"].widget.attrs.setdefault(
            "class", "w-full min-w-[12rem] max-w-md border border-slate-300 rounded-lg px-2 py-1.5 bg-white text-slate-900"
        )
        self.fields["supplier_order_number"].widget.attrs.setdefault(
            "class", "w-full max-w-xs border border-slate-300 rounded-lg px-2 py-1.5 text-slate-900"
        )


class BaseCatalogProductSupplierFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        active_supplier_ids: list[int] = []
        preferred_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            data = form.cleaned_data
            if not data or data.get("DELETE"):
                continue
            supplier = data.get("supplier")
            if supplier is None:
                continue
            sid = supplier.pk
            if sid in active_supplier_ids:
                raise forms.ValidationError(
                    _("Each supplier can only appear once. Remove the duplicate row or pick another supplier.")
                )
            active_supplier_ids.append(sid)
            if data.get("is_preferred"):
                preferred_count += 1

        if not active_supplier_ids:
            raise forms.ValidationError(
                _("Add at least one supplier. Use a separate row per supplier with their own cost and order number.")
            )
        if preferred_count > 1:
            raise forms.ValidationError(
                _("Choose only one preferred supplier (used as the default on the price list and in proposals).")
            )


CatalogProductSupplierFormSet = inlineformset_factory(
    Product,
    ProductSupplier,
    form=CatalogProductSupplierOfferForm,
    formset=BaseCatalogProductSupplierFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


def primary_supplier_row_from_formset(formset: BaseCatalogProductSupplierFormSet):
    """
    After is_valid(), pick preferred row or first active row for Product.supplier / cost / order mirror.
    """
    preferred = None
    first = None
    for form in formset.forms:
        if not hasattr(form, "cleaned_data"):
            continue
        data = form.cleaned_data
        if not data or data.get("DELETE"):
            continue
        supplier = data.get("supplier")
        if supplier is None:
            continue
        row = {
            "supplier": supplier,
            "cost_price": data.get("cost_price"),
            "supplier_order_number": (data.get("supplier_order_number") or "")[:255],
        }
        if first is None:
            first = row
        if data.get("is_preferred"):
            preferred = row
    return preferred or first


def ensure_preferred_product_supplier_offer(product_id: int) -> None:
    """If no row is preferred, mark the first offer preferred (ProductSupplier.save syncs Product fields)."""
    qs = ProductSupplier.objects.filter(product_id=product_id).order_by("sort_order", "pk")
    if not qs.exists():
        return
    if not qs.filter(is_preferred=True).exists():
        first = qs.first()
        first.is_preferred = True
        first.save(update_fields=["is_preferred"])


class CatalogCombinationForm(forms.ModelForm):
    class Meta:
        model = Combination
        fields = [
            "name",
            "description",
            "usps",
            "image",
            "offer_type",
            "offer_fixed_amount",
            "discount_amount",
            "discount_percentage",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget.attrs.setdefault("rows", 3)
        self.fields["usps"].widget.attrs.setdefault("rows", 3)
        _style_form_widgets(self.fields)


class CatalogCombinationItemForm(forms.ModelForm):
    class Meta:
        model = CombinationItem
        fields = ["product", "sort_order", "selected_options"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(show_in_price_list=True).order_by(
            "brand", "model_type"
        )
        product_id = getattr(self.instance, "product_id", None) if self.instance and self.instance.pk else None
        if product_id is None and self.data and self.prefix:
            raw = self.data.get(f"{self.prefix}-product")
            if raw:
                try:
                    product_id = int(raw)
                except (TypeError, ValueError):
                    pass
        if product_id:
            option_pks = list(
                ProductOption.objects.filter(main_product_id=product_id).values_list(
                    "option_product_id", flat=True
                )
            )
            if option_pks:
                self.fields["selected_options"].queryset = Product.objects.filter(pk__in=option_pks).order_by(
                    "brand", "model_type"
                )
            else:
                self.fields["selected_options"].queryset = Product.objects.none()
        else:
            self.fields["selected_options"].queryset = Product.objects.none()
        self.fields["selected_options"].widget = forms.CheckboxSelectMultiple(
            attrs={"class": "space-y-1 text-sm"}
        )
        self.fields["selected_options"].required = False
        if "product" in self.fields:
            self.fields["product"].widget.attrs.setdefault(
                "class", "w-full max-w-xl border border-slate-300 rounded-lg px-3 py-2 bg-white"
            )
        if "sort_order" in self.fields:
            self.fields["sort_order"].widget.attrs.setdefault(
                "class", "w-24 border border-slate-300 rounded-lg px-3 py-2"
            )


CatalogCombinationItemFormSet = inlineformset_factory(
    Combination,
    CombinationItem,
    form=CatalogCombinationItemForm,
    extra=1,
    can_delete=True,
)


def refresh_combination_sales_price(combination: Combination) -> None:
    c = (
        Combination.objects.filter(pk=combination.pk)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=CombinationItem.objects.prefetch_related("selected_options"),
            )
        )
        .first()
    )
    if c is None:
        return
    price = c.offer_price
    if price is not None:
        Combination.objects.filter(pk=c.pk).update(combination_sales_price=price)
