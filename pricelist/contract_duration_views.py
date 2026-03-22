"""Frontend CRUD for contract durations (maintenance periods on proposals)."""

from __future__ import annotations

from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from .contract_duration_forms import ContractDurationForm
from .frontend_access import require_capability
from .models import ContractDuration


@require_http_methods(["GET"])
@require_capability("access_proposals")
def contract_duration_list_view(request):
    durations = ContractDuration.objects.all().order_by("duration_months", "name")
    return render(
        request,
        "pricelist/contract_duration_list.html",
        {
            "page_title": _("Contract durations"),
            "page_subtitle": _("Maintenance contract options shown on the proposal (e.g. 3 years, 5 years)."),
            "contract_durations": durations,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("access_proposals")
def contract_duration_create_view(request):
    if request.method == "POST":
        form = ContractDurationForm(request.POST)
        if form.is_valid():
            row = form.save()
            messages.success(request, _("Contract duration created."))
            return redirect("pricelist:contract_duration_edit", duration_uuid=row.uuid)
    else:
        form = ContractDurationForm()
    return render(
        request,
        "pricelist/contract_duration_form.html",
        {
            "page_title": _("Add contract duration"),
            "page_subtitle": _("Define period, fees, and how this option contributes to contract totals on the proposal."),
            "form": form,
            "is_new": True,
            "duration_obj": None,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability("access_proposals")
def contract_duration_edit_view(request, duration_uuid):
    obj = get_object_or_404(ContractDuration, uuid=duration_uuid)
    if request.method == "POST":
        form = ContractDurationForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, _("Contract duration saved."))
            return redirect("pricelist:contract_duration_list")
    else:
        form = ContractDurationForm(instance=obj)
    return render(
        request,
        "pricelist/contract_duration_form.html",
        {
            "page_title": _("Edit contract duration"),
            "page_subtitle": obj.name,
            "form": form,
            "is_new": False,
            "duration_obj": obj,
        },
    )


@require_POST
@require_capability("access_proposals")
def contract_duration_delete_view(request, duration_uuid):
    obj = get_object_or_404(ContractDuration, uuid=duration_uuid)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(
            request,
            _("Cannot remove this contract duration: it is still referenced elsewhere."),
        )
        return redirect("pricelist:contract_duration_list")
    messages.success(request, _("Contract duration removed."))
    return redirect("pricelist:contract_duration_list")
