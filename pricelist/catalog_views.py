"""
Frontend catalog management: products, combinations, image library, soft delete & staff trash.
"""

from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from .catalog_forms import (
    CatalogCombinationForm,
    CatalogCombinationItemFormSet,
    CatalogProductForm,
    CatalogProductSupplierFormSet,
    ensure_preferred_product_supplier_offer,
    primary_supplier_row_from_formset,
    refresh_combination_sales_price,
)
from .frontend_access import get_capabilities, require_capability
from .models import Combination, CombinationItem, Product, ProductOption, ProductSupplier


def _product_label(p: Product) -> str:
    return (f"{p.brand or ''} {p.model_type or ''}".strip()) or f"Product #{p.pk}"


@require_http_methods(["GET", "POST"])
@require_capability("access_catalog")
def catalog_product_list_view(request):
    products = (
        Product.objects.select_related("supplier", "category", "profit_profile")
        .order_by("brand", "model_type", "pk")
    )
    return render(
        request,
        "pricelist/catalog_product_list.html",
        {
            "page_title": _("Products"),
            "page_subtitle": _("Manage catalog products. Removing hides them from the price list."),
            "products": products,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("catalog_change")
def catalog_product_create_view(request):
    shared = Product()
    if request.method == "POST":
        form = CatalogProductForm(request.POST, request.FILES, instance=shared)
        formset = CatalogProductSupplierFormSet(request.POST, request.FILES, instance=shared)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                row = primary_supplier_row_from_formset(formset)
                product = form.save(commit=False)
                product.supplier = row["supplier"]
                product.cost_price = row["cost_price"]
                product.supplier_order_number = row["supplier_order_number"]
                product.deleted_at = None
                product.save()
                form.save_m2m()
                formset.instance = product
                formset.save()
                ensure_preferred_product_supplier_offer(product.pk)
            messages.success(request, _("Product created."))
            return redirect("pricelist:catalog_product_edit", article_uuid=product.article_number)
    else:
        form = CatalogProductForm(instance=shared)
        formset = CatalogProductSupplierFormSet(instance=shared)
    return render(
        request,
        "pricelist/catalog_product_form.html",
        {
            "page_title": _("Add product"),
            "page_subtitle": _("Create a new catalog product."),
            "form": form,
            "supplier_formset": formset,
            "is_new": True,
            "product": None,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("catalog_change")
def catalog_product_edit_view(request, article_uuid):
    product = get_object_or_404(Product.all_objects, article_number=article_uuid)
    cap = get_capabilities(request.user)
    if product.deleted_at and not (cap.catalog_change or cap.catalog_trash):
        raise Http404()
    if product.deleted_at:
        messages.warning(request, _("This product is removed from the catalog. Restore it from Trash (staff)."))

    def _ensure_offers_from_legacy():
        if not product.product_suppliers.exists() and product.supplier_id:
            ProductSupplier.objects.create(
                product=product,
                supplier_id=product.supplier_id,
                cost_price=product.cost_price,
                supplier_order_number=(product.supplier_order_number or "")[:255],
                is_preferred=True,
                sort_order=0,
            )

    if request.method == "POST":
        form = CatalogProductForm(request.POST, request.FILES, instance=product)
        formset = CatalogProductSupplierFormSet(request.POST, request.FILES, instance=product)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                row = primary_supplier_row_from_formset(formset)
                saved = form.save(commit=False)
                saved.supplier = row["supplier"]
                saved.cost_price = row["cost_price"]
                saved.supplier_order_number = row["supplier_order_number"]
                saved.save()
                form.save_m2m()
                formset.save()
                ensure_preferred_product_supplier_offer(saved.pk)
            messages.success(request, _("Product saved."))
            return redirect("pricelist:catalog_product_edit", article_uuid=product.article_number)
    else:
        _ensure_offers_from_legacy()
        form = CatalogProductForm(instance=product)
        formset = CatalogProductSupplierFormSet(instance=product)
    return render(
        request,
        "pricelist/catalog_product_form.html",
        {
            "page_title": _("Edit product"),
            "page_subtitle": _product_label(product),
            "form": form,
            "supplier_formset": formset,
            "is_new": False,
            "product": product,
        },
    )


@require_POST
@require_capability("catalog_soft_delete")
def catalog_product_remove_view(request, article_uuid):
    product = get_object_or_404(Product.objects, article_number=article_uuid)
    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at"])
    messages.success(request, _("Product removed from the catalog. It can be restored by an administrator."))
    return redirect("pricelist:catalog_product_list")


@require_http_methods(["GET"])
@require_capability("catalog_trash")
def catalog_product_trash_view(request):
    products = (
        Product.all_objects.filter(deleted_at__isnull=False)
        .select_related("supplier", "category")
        .order_by("-deleted_at")
    )
    return render(
        request,
        "pricelist/catalog_trash_products.html",
        {
            "page_title": _("Removed products"),
            "page_subtitle": _("Restore items to the catalog or delete them permanently."),
            "products": products,
        },
    )


@require_POST
@require_capability("catalog_trash")
def catalog_product_restore_view(request, article_uuid):
    product = get_object_or_404(Product.all_objects, article_number=article_uuid, deleted_at__isnull=False)
    product.deleted_at = None
    product.save(update_fields=["deleted_at"])
    messages.success(request, _("Product restored."))
    return redirect("pricelist:catalog_product_trash")


@require_POST
@require_capability("catalog_purge")
def catalog_product_purge_view(request, article_uuid):
    product = get_object_or_404(Product.all_objects, article_number=article_uuid, deleted_at__isnull=False)
    if product.image:
        product.image.delete(save=False)
    product.delete()
    messages.success(request, _("Product permanently deleted."))
    return redirect("pricelist:catalog_product_trash")


# --- Combinations ---


@require_http_methods(["GET", "POST"])
@require_capability("access_catalog")
def catalog_combination_list_view(request):
    combinations = Combination.objects.all().order_by("name")
    return render(
        request,
        "pricelist/catalog_combination_list.html",
        {
            "page_title": _("Combinations"),
            "page_subtitle": _("Manage packages and bundles."),
            "combinations": combinations,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("catalog_change")
def catalog_combination_create_view(request):
    if request.method == "POST":
        form = CatalogCombinationForm(request.POST, request.FILES)
        formset = CatalogCombinationItemFormSet(request.POST, instance=Combination())
        if form.is_valid():
            combo = form.save(commit=False)
            combo.combination_sales_price = Decimal("0.01")
            combo.deleted_at = None
            combo.save()
            formset = CatalogCombinationItemFormSet(request.POST, instance=combo)
            if formset.is_valid():
                with transaction.atomic():
                    formset.save()
                    refresh_combination_sales_price(combo)
                messages.success(request, _("Combination created."))
                return redirect("pricelist:catalog_combination_edit", combo_uuid=combo.uuid)
            combo.delete()
            messages.error(request, _("Fix the errors in the line items below."))
            formset = CatalogCombinationItemFormSet(request.POST, instance=Combination())
    else:
        form = CatalogCombinationForm()
        formset = CatalogCombinationItemFormSet(instance=Combination())
    return render(
        request,
        "pricelist/catalog_combination_form.html",
        {
            "page_title": _("Add combination"),
            "page_subtitle": _("Create a package: add one or more products below."),
            "form": form,
            "formset": formset,
            "is_new": True,
            "combination": None,
            "product_ids_with_options": list(
                ProductOption.objects.values_list("main_product_id", flat=True).distinct()
            ),
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("catalog_change")
def catalog_combination_edit_view(request, combo_uuid):
    combination = get_object_or_404(Combination.all_objects, uuid=combo_uuid)
    cap = get_capabilities(request.user)
    if combination.deleted_at and not (cap.catalog_change or cap.catalog_trash):
        raise Http404()
    if combination.deleted_at:
        messages.warning(
            request, _("This combination is removed from the catalog. Restore it from Trash (staff).")
        )
    if request.method == "POST":
        form = CatalogCombinationForm(request.POST, request.FILES, instance=combination)
        formset = CatalogCombinationItemFormSet(request.POST, instance=combination)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                refresh_combination_sales_price(combination)
            messages.success(request, _("Combination saved."))
            return redirect("pricelist:catalog_combination_edit", combo_uuid=combination.uuid)
    else:
        form = CatalogCombinationForm(instance=combination)
        formset = CatalogCombinationItemFormSet(instance=combination)
    return render(
        request,
        "pricelist/catalog_combination_form.html",
        {
            "page_title": _("Edit combination"),
            "page_subtitle": combination.name,
            "form": form,
            "formset": formset,
            "is_new": False,
            "combination": combination,
            "product_ids_with_options": list(
                ProductOption.objects.values_list("main_product_id", flat=True).distinct()
            ),
        },
    )


@require_POST
@require_capability("catalog_soft_delete")
def catalog_combination_remove_view(request, combo_uuid):
    combo = get_object_or_404(Combination.objects, uuid=combo_uuid)
    combo.deleted_at = timezone.now()
    combo.save(update_fields=["deleted_at"])
    messages.success(
        request, _("Combination removed from the catalog. It can be restored by an administrator.")
    )
    return redirect("pricelist:catalog_combination_list")


@require_http_methods(["GET"])
@require_capability("catalog_trash")
def catalog_combination_trash_view(request):
    combinations = Combination.all_objects.filter(deleted_at__isnull=False).order_by("-deleted_at")
    return render(
        request,
        "pricelist/catalog_trash_combinations.html",
        {
            "page_title": _("Removed combinations"),
            "page_subtitle": _("Restore or permanently delete."),
            "combinations": combinations,
        },
    )


@require_POST
@require_capability("catalog_trash")
def catalog_combination_restore_view(request, combo_uuid):
    combo = get_object_or_404(Combination.all_objects, uuid=combo_uuid, deleted_at__isnull=False)
    combo.deleted_at = None
    combo.save(update_fields=["deleted_at"])
    messages.success(request, _("Combination restored."))
    return redirect("pricelist:catalog_combination_trash")


@require_POST
@require_capability("catalog_purge")
def catalog_combination_purge_view(request, combo_uuid):
    combo = get_object_or_404(Combination.all_objects, uuid=combo_uuid, deleted_at__isnull=False)
    if combo.image:
        combo.image.delete(save=False)
    combo.delete()
    messages.success(request, _("Combination permanently deleted."))
    return redirect("pricelist:catalog_combination_trash")


# --- Image library ---


def _media_path(relative: str) -> str:
    return os.path.normpath(os.path.join(str(settings.MEDIA_ROOT), relative.replace("/", os.sep)))


def _safe_under_media(abs_path: str) -> bool:
    root = os.path.normpath(str(settings.MEDIA_ROOT))
    try:
        common = os.path.commonpath([root, os.path.normpath(abs_path)])
    except ValueError:
        return False
    return common == root


def _build_image_inventory():
    rows = []
    seen_paths: set[str] = set()

    def add_row(rel_path: str, kind: str, label: str, edit_url: str | None, obj_created):
        if not rel_path:
            return
        norm = rel_path.replace("\\", "/").lstrip("/")
        full = _media_path(norm)
        size = None
        mtime = None
        if os.path.isfile(full):
            try:
                st = os.stat(full)
                size = st.st_size
                mtime = timezone.datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone())
            except OSError:
                pass
        seen_paths.add(norm)
        rows.append(
            {
                "relative_path": norm,
                "kind": kind,
                "label": label,
                "edit_url": edit_url,
                "size": size,
                "mtime": mtime,
                "created_on_catalog": obj_created,
                "is_unused": kind == "orphan",
                "file_exists": os.path.isfile(full),
            }
        )

    for p in Product.all_objects.exclude(Q(image__isnull=True) | Q(image="")).order_by("pk"):
        add_row(
            p.image.name,
            "product",
            _product_label(p),
            reverse("pricelist:catalog_product_edit", kwargs={"article_uuid": p.article_number}),
            p.created_at,
        )

    for c in Combination.all_objects.exclude(Q(image__isnull=True) | Q(image="")).order_by("pk"):
        add_row(
            c.image.name,
            "combination",
            c.name,
            reverse("pricelist:catalog_combination_edit", kwargs={"combo_uuid": c.uuid}),
            None,
        )

    orphan_rows = []
    for sub in ("product_images", "combination_images"):
        d = _media_path(sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            fp = os.path.join(d, name)
            if not os.path.isfile(fp):
                continue
            rel = f"{sub}/{name}".replace("\\", "/")
            if rel in seen_paths:
                continue
            size = None
            mtime = None
            try:
                st = os.stat(fp)
                size = st.st_size
                mtime = timezone.datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone())
            except OSError:
                pass
            orphan_rows.append(
                {
                    "relative_path": rel,
                    "kind": "orphan",
                    "label": str(_("Unused file")),
                    "edit_url": None,
                    "size": size,
                    "mtime": mtime,
                    "created_on_catalog": None,
                    "is_unused": True,
                    "file_exists": os.path.isfile(fp),
                }
            )

    rows.sort(key=lambda r: (r["kind"] == "orphan", r["label"].lower()))
    return rows + orphan_rows


def _normalize_catalog_image_rel(raw: str) -> str | None:
    rel = (raw or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel:
        return None
    if not rel.startswith(("product_images/", "combination_images/")):
        return None
    full = _media_path(rel)
    if not _safe_under_media(full):
        return None
    return rel


def _delete_catalog_image(rel: str) -> str:
    """
    Clear every product/combination referencing this path, then remove the file if present.
    Returns a short outcome token for messaging: deleted_file, cleared_refs, orphan_deleted,
    file_missing_after_clear, disk_error.
    """
    full = _media_path(rel)
    had_refs = False
    for p in Product.all_objects.exclude(Q(image__isnull=True) | Q(image="")):
        if p.image.name == rel:
            had_refs = True
            p.image.delete(save=False)
            p.image = None
            p.save(update_fields=["image"])
    for c in Combination.all_objects.exclude(Q(image__isnull=True) | Q(image="")):
        if c.image.name == rel:
            had_refs = True
            c.image.delete(save=False)
            c.image = None
            c.save(update_fields=["image"])

    if os.path.isfile(full):
        try:
            os.remove(full)
            return "deleted_file" if had_refs else "orphan_deleted"
        except OSError:
            return "disk_error"
    if had_refs:
        return "cleared_refs"
    return "file_missing_after_clear"


@require_http_methods(["GET", "POST"])
@require_capability("access_catalog")
def catalog_image_list_view(request):
    if request.method == "POST":
        if not get_capabilities(request.user).catalog_change:
            raise PermissionDenied(_("You do not have permission to change catalog images."))
        paths_raw = request.POST.getlist("delete_paths")
        if not paths_raw:
            single = request.POST.get("delete_path")
            if single:
                paths_raw = [single]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in paths_raw:
            rel = _normalize_catalog_image_rel(raw)
            if rel and rel not in seen:
                seen.add(rel)
                normalized.append(rel)

        if not normalized:
            messages.error(request, _("Invalid path."))
            return redirect("pricelist:catalog_image_list")

        outcomes: dict[str, int] = {}
        for rel in normalized:
            token = _delete_catalog_image(rel)
            outcomes[token] = outcomes.get(token, 0) + 1

        n = len(normalized)
        if n == 1:
            tok = next(iter(outcomes))
            if tok == "deleted_file":
                messages.success(request, _("Image file deleted."))
            elif tok == "orphan_deleted":
                messages.success(request, _("Orphan file deleted."))
            elif tok == "cleared_refs":
                messages.success(request, _("Image reference cleared."))
            elif tok == "disk_error":
                messages.warning(request, _("File could not be removed from disk."))
            else:
                messages.warning(request, _("File not found on disk (references were cleared if any)."))
        else:
            deleted = outcomes.get("deleted_file", 0) + outcomes.get("orphan_deleted", 0)
            cleared = outcomes.get("cleared_refs", 0)
            errors = outcomes.get("disk_error", 0)
            missing = outcomes.get("file_missing_after_clear", 0)
            parts = []
            if deleted:
                parts.append(_("%(count)s file(s) removed from disk.") % {"count": deleted})
            if cleared:
                parts.append(_("%(count)s reference(s) cleared (file already gone).") % {"count": cleared})
            if missing:
                parts.append(_("%(count)s path(s) had no file on disk.") % {"count": missing})
            if errors:
                parts.append(_("%(count)s file(s) could not be removed from disk.") % {"count": errors})
            if parts:
                level = messages.warning if errors else messages.success
                level(request, " ".join(str(p) for p in parts))
            else:
                messages.info(request, _("No changes."))

        return redirect("pricelist:catalog_image_list")

    inventory = _build_image_inventory()
    total_bytes = sum((r["size"] or 0) for r in inventory)
    unused_count = sum(1 for r in inventory if r.get("is_unused"))
    return render(
        request,
        "pricelist/catalog_image_list.html",
        {
            "page_title": _("Image library"),
            "page_subtitle": _("Stored images, where they are used, and disk usage. Delete files here to free space."),
            "inventory": inventory,
            "total_bytes": total_bytes,
            "unused_count": unused_count,
            "media_url": settings.MEDIA_URL,
        },
    )
