"""Frontend views for Contacts (CRM): organizations by role and person directory."""

from django.contrib import messages
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from urllib.parse import quote

from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from .contacts_forms import (
    DepartmentForm,
    OrganizationForm,
    OrganizationNetworkLinkForm,
    OrganizationPersonForm,
    PersonEventFormSet,
    PersonForm,
    PersonHobbyFormSet,
    PersonLifeEventForm,
    PersonOrganizationMembershipForm,
)
from .models import (
    Department,
    Organization,
    OrganizationNetworkLink,
    OrganizationRole,
    Person,
    PersonEvent,
    PersonHobby,
)
from .services import contacts_service as contacts_svc
from .services.organization_identity import identity_check_payload


def _section_from_request(request, default: str) -> str:
    return request.GET.get("from") or default


def _redirect_org_detail(org: Organization, from_section: str):
    url = reverse("pricelist:contacts_organization_detail", kwargs={"org_uuid": org.uuid})
    if from_section:
        return redirect(f"{url}?{urlencode({'from': from_section})}")
    return redirect(url)


def _org_list(request, *, role: str, section: str, title: str, subtitle: str):
    organizations = contacts_svc.organizations_with_role(role)
    return render(
        request,
        "pricelist/contacts_organization_list.html",
        {
            "contacts_section": section,
            "page_title": title,
            "page_subtitle": subtitle,
            "from_param": section,
            "organizations": organizations,
        },
    )


def contacts_suppliers_view(request):
    return _org_list(
        request,
        role=OrganizationRole.ROLE_SUPPLIER,
        section="suppliers",
        title=_("Suppliers"),
        subtitle=_("Organizations with the supplier role, departments, and linked persons."),
    )


def contacts_clients_view(request):
    return _org_list(
        request,
        role=OrganizationRole.ROLE_CLIENT,
        section="clients",
        title=_("Clients"),
        subtitle=_("Client organizations with full company profile, departments, and contacts."),
    )


def contacts_leads_view(request):
    return _org_list(
        request,
        role=OrganizationRole.ROLE_LEAD,
        section="leads",
        title=_("Leads"),
        subtitle=_("Pipeline leads (same detail as clients, plus pipeline status)."),
    )


def contacts_network_view(request):
    return _org_list(
        request,
        role=OrganizationRole.ROLE_NETWORK,
        section="network",
        title=_("Network"),
        subtitle=_("Partners and network relationships."),
    )


def contacts_persons_view(request):
    persons = contacts_svc.persons_directory()
    return render(
        request,
        "pricelist/contacts_persons.html",
        {
            "contacts_section": "persons",
            "page_title": _("Persons"),
            "persons": persons,
        },
    )


def contacts_organization_detail_view(request, org_uuid):
    organization = get_object_or_404(
        Organization.objects.prefetch_related(
            "departments",
            "memberships__person",
            "memberships__department",
            "role_assignments",
            "network_partner_links__linked_organization__role_assignments",
            "counterparty_network_links__network_organization__role_assignments",
        ),
        uuid=org_uuid,
    )
    section = _section_from_request(request, "clients")
    variant_map = {
        "suppliers": "suppliers",
        "clients": "clients",
        "leads": "leads",
        "network": "network",
        "persons": "clients",
    }
    variant = variant_map.get(section, "clients")
    ctx = contacts_svc.organization_detail_bundle(organization, variant=variant)
    ctx["contacts_section"] = section
    ctx["back_section"] = section
    ctx["return_from"] = section
    next_path = reverse("pricelist:contacts_organization_detail", kwargs={"org_uuid": organization.uuid})
    next_full = f"{next_path}?{urlencode({'from': section})}"
    ctx["person_create_next"] = quote(next_full, safe="/")
    return render(request, "pricelist/contacts_organization_detail.html", ctx)


def contacts_person_detail_view(request, person_uuid):
    person = get_object_or_404(
        Person.objects.prefetch_related(
            "life_events",
            "memberships__organization",
            "memberships__department",
            Prefetch("hobbies", queryset=PersonHobby.objects.order_by("sort_order", "name", "id")),
            Prefetch("personal_events", queryset=PersonEvent.objects.order_by("event_date", "name", "id")),
        ),
        uuid=person_uuid,
    )
    ctx = contacts_svc.person_detail_bundle(person)
    ctx["contacts_section"] = "persons"
    return render(request, "pricelist/contacts_person_detail.html", ctx)


@require_GET
def contacts_organization_identity_check_view(request):
    """JSON: live duplicate check for VAT / Chamber of Commerce number."""
    data = identity_check_payload(
        vat=request.GET.get("vat", ""),
        coc=request.GET.get("coc", ""),
        exclude_organization_uuid=request.GET.get("exclude_uuid") or None,
    )
    return JsonResponse(data)


def _preset_roles_from_query(request) -> list[str]:
    preset = request.GET.get("preset")
    mapping = {
        "suppliers": [OrganizationRole.ROLE_SUPPLIER],
        "clients": [OrganizationRole.ROLE_CLIENT],
        "leads": [OrganizationRole.ROLE_LEAD],
        "network": [OrganizationRole.ROLE_NETWORK],
    }
    return mapping.get(preset or "", [])


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_organization_create_view(request):
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    return_next = request.GET.get("next") or request.POST.get("return_next") or ""
    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            org = form.save()
            messages.success(request, _("Organization created."))
            if return_next and return_next.startswith("/") and not return_next.startswith("//"):
                return redirect(return_next)
            return _redirect_org_detail(org, return_from)
    else:
        form = OrganizationForm(initial={"roles": _preset_roles_from_query(request)})
    return render(
        request,
        "pricelist/contacts_organization_form.html",
        {
            "form": form,
            "is_new": True,
            "return_from": return_from,
            "return_next": return_next,
            "page_title": _("Add organization"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_organization_edit_view(request, org_uuid):
    organization = get_object_or_404(Organization, uuid=org_uuid)
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    if request.method == "POST":
        form = OrganizationForm(request.POST, instance=organization)
        if form.is_valid():
            form.save()
            messages.success(request, _("Organization updated."))
            return _redirect_org_detail(organization, return_from)
    else:
        form = OrganizationForm(instance=organization)
    return render(
        request,
        "pricelist/contacts_organization_form.html",
        {
            "form": form,
            "is_new": False,
            "organization": organization,
            "return_from": return_from,
            "return_next": "",
            "page_title": _("Edit organization"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_person_membership_add_view(request, person_uuid):
    """Add company + department link starting from the person detail page."""
    person = get_object_or_404(Person, uuid=person_uuid)
    if request.method == "POST":
        form = PersonOrganizationMembershipForm(request.POST, person=person)
        if form.is_valid():
            form.save()
            messages.success(request, _("Company link added."))
            return redirect("pricelist:contacts_person_detail", person_uuid=person.uuid)
    else:
        form = PersonOrganizationMembershipForm(person=person)

    departments_by_org = {}
    for d in Department.objects.select_related("organization").order_by("name"):
        departments_by_org.setdefault(d.organization_id, []).append({"id": d.pk, "name": d.name})

    org_create_path = reverse("pricelist:contacts_organization_create")
    membership_path = reverse("pricelist:contacts_person_membership_add", kwargs={"person_uuid": person.uuid})
    org_create_next = f"{org_create_path}?{urlencode({'from': 'persons', 'next': membership_path})}"

    return render(
        request,
        "pricelist/contacts_person_membership_form.html",
        {
            "form": form,
            "person": person,
            "departments_by_org": departments_by_org,
            "organization_create_href": org_create_next,
            "page_title": _("Link to company"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_person_create_view(request):
    return_next = request.GET.get("next") or request.POST.get("return_next") or ""
    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            person = form.save()
            # Only allow same-site relative redirects (avoid open redirects).
            if return_next and return_next.startswith("/") and not return_next.startswith("//"):
                messages.success(request, _("Person created."))
                return redirect(return_next)
            messages.success(
                request,
                _("Person created. Add hobbies, interests, and events below, then save."),
            )
            return redirect("pricelist:contacts_person_edit", person_uuid=person.uuid)
    else:
        form = PersonForm()
    return render(
        request,
        "pricelist/contacts_person_form.html",
        {
            "form": form,
            "is_new": True,
            "return_next": return_next,
            "page_title": _("Add person"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_person_edit_view(request, person_uuid):
    person = get_object_or_404(Person, uuid=person_uuid)
    if request.method == "POST":
        form = PersonForm(request.POST, instance=person)
        hobby_formset = PersonHobbyFormSet(request.POST, instance=person, prefix="hobbies")
        event_formset = PersonEventFormSet(request.POST, instance=person, prefix="events")
        if form.is_valid() and hobby_formset.is_valid() and event_formset.is_valid():
            form.save()
            hobby_formset.save()
            event_formset.save()
            messages.success(request, _("Person updated."))
            return redirect("pricelist:contacts_person_detail", person_uuid=person.uuid)
    else:
        form = PersonForm(instance=person)
        hobby_formset = PersonHobbyFormSet(instance=person, prefix="hobbies")
        event_formset = PersonEventFormSet(instance=person, prefix="events")
    return render(
        request,
        "pricelist/contacts_person_form.html",
        {
            "form": form,
            "hobby_formset": hobby_formset,
            "event_formset": event_formset,
            "is_new": False,
            "person": person,
            "return_next": "",
            "page_title": _("Edit person"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_department_create_view(request, org_uuid):
    organization = get_object_or_404(Organization, uuid=org_uuid)
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    if request.method == "POST":
        form = DepartmentForm(request.POST, organization=organization)
        if form.is_valid():
            form.save()
            messages.success(request, _("Department added."))
            return _redirect_org_detail(organization, return_from)
    else:
        form = DepartmentForm(organization=organization)
    return render(
        request,
        "pricelist/contacts_department_form.html",
        {
            "form": form,
            "organization": organization,
            "department": None,
            "return_from": return_from,
            "page_title": _("Add department"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_department_edit_view(request, org_uuid, dept_uuid):
    organization = get_object_or_404(Organization, uuid=org_uuid)
    department = get_object_or_404(Department, uuid=dept_uuid, organization=organization)
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department, organization=organization)
        if form.is_valid():
            form.save()
            messages.success(request, _("Department updated."))
            return _redirect_org_detail(organization, return_from)
    else:
        form = DepartmentForm(instance=department, organization=organization)
    return render(
        request,
        "pricelist/contacts_department_form.html",
        {
            "form": form,
            "organization": organization,
            "department": department,
            "return_from": return_from,
            "page_title": _("Edit department"),
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_membership_create_view(request, org_uuid):
    organization = get_object_or_404(Organization, uuid=org_uuid)
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    next_path = reverse("pricelist:contacts_organization_detail", kwargs={"org_uuid": organization.uuid})
    next_full = f"{next_path}?{urlencode({'from': return_from})}"
    person_create_next = quote(next_full, safe="/")
    if request.method == "POST":
        form = OrganizationPersonForm(request.POST, organization=organization)
        if form.is_valid():
            form.save()
            messages.success(request, _("Contact link added."))
            return _redirect_org_detail(organization, return_from)
    else:
        form = OrganizationPersonForm(organization=organization)
    return render(
        request,
        "pricelist/contacts_membership_form.html",
        {
            "form": form,
            "organization": organization,
            "return_from": return_from,
            "person_create_next": person_create_next,
            "page_title": _("Link person to organization"),
        },
    )


def _network_link_form_mode(organization: Organization, section: str) -> str:
    """Pure helper: do not decorate with require_http_methods (it is not a view)."""
    codes = {r.role for r in organization.role_assignments.all()}
    if OrganizationRole.ROLE_NETWORK in codes and section == "network":
        return "network_anchor"
    return "counterparty_anchor"


@require_http_methods(["GET", "HEAD", "POST"])
def contacts_network_link_add_view(request, org_uuid):
    organization = get_object_or_404(
        Organization.objects.prefetch_related("role_assignments"),
        uuid=org_uuid,
    )
    return_from = request.GET.get("from") or request.POST.get("return_from") or "clients"
    mode = _network_link_form_mode(organization, return_from)
    if request.method == "POST":
        form = OrganizationNetworkLinkForm(
            request.POST,
            mode=mode,
            anchor_organization=organization,
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Network link saved."))
            return _redirect_org_detail(organization, return_from)
    else:
        form = OrganizationNetworkLinkForm(mode=mode, anchor_organization=organization)
    return render(
        request,
        "pricelist/contacts_network_link_form.html",
        {
            "form": form,
            "organization": organization,
            "return_from": return_from,
            "network_link_mode": mode,
            "page_title": (
                _("Link company to this network partner")
                if mode == "network_anchor"
                else _("Link network partner to this company")
            ),
        },
    )


@require_http_methods(["POST"])
def contacts_network_link_delete_view(request, org_uuid, link_uuid):
    organization = get_object_or_404(Organization, uuid=org_uuid)
    link = get_object_or_404(
        OrganizationNetworkLink,
        uuid=link_uuid,
    )
    return_from = request.POST.get("return_from") or "clients"
    if link.network_organization_id != organization.pk and link.linked_organization_id != organization.pk:
        messages.error(request, _("This link does not belong to the current organization."))
        return _redirect_org_detail(organization, return_from)
    link.delete()
    messages.success(request, _("Network link removed."))
    return _redirect_org_detail(organization, return_from)


def contacts_life_event_create_view(request, person_uuid):
    person = get_object_or_404(Person, uuid=person_uuid)
    if request.method == "POST":
        form = PersonLifeEventForm(request.POST, person=person)
        if form.is_valid():
            form.save()
            messages.success(request, _("Life event added."))
            return redirect("pricelist:contacts_person_detail", person_uuid=person.uuid)
    else:
        form = PersonLifeEventForm(person=person)
    return render(
        request,
        "pricelist/contacts_life_event_form.html",
        {
            "form": form,
            "person": person,
            "page_title": _("Add life event"),
        },
    )
