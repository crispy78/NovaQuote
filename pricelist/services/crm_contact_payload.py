"""Nested JSON for proposal/product contact pickers (client–lead and supplier orgs)."""

from __future__ import annotations

from django.db.models import Prefetch

from ..models import Department, Organization, OrganizationPerson, OrganizationRole


def _org_payload(
    queryset,
) -> list[dict]:
    out = []
    for o in queryset:
        depts = list(o.departments.all())
        members = list(o.memberships.all())
        out.append(
            {
                "uuid": str(o.uuid),
                "name": o.name,
                "departments": [{"uuid": str(d.uuid), "name": d.name} for d in depts],
                "memberships": [
                    {
                        "uuid": str(m.uuid),
                        "label": (f"{m.person.first_name} {m.person.last_name}".strip() or str(m.person_id)),
                        "department_uuid": str(m.department.uuid) if m.department_id else None,
                    }
                    for m in members
                ],
            }
        )
    return out


def client_lead_contact_picker_payload() -> list[dict]:
    """Organizations with Client or Lead role, with departments and linked persons."""
    qs = (
        Organization.objects.filter(
            role_assignments__role__in=[
                OrganizationRole.ROLE_CLIENT,
                OrganizationRole.ROLE_LEAD,
            ]
        )
        .distinct()
        .prefetch_related(
            Prefetch("departments", queryset=Department.objects.order_by("name")),
            Prefetch(
                "memberships",
                queryset=OrganizationPerson.objects.select_related("person", "department").order_by(
                    "person__last_name", "person__first_name"
                ),
            ),
        )
        .order_by("name")
    )
    return _org_payload(qs)


def supplier_contact_picker_payload() -> list[dict]:
    """Organizations with Supplier role (for catalog product CRM links)."""
    qs = (
        Organization.objects.filter(role_assignments__role=OrganizationRole.ROLE_SUPPLIER)
        .distinct()
        .prefetch_related(
            Prefetch("departments", queryset=Department.objects.order_by("name")),
            Prefetch(
                "memberships",
                queryset=OrganizationPerson.objects.select_related("person", "department").order_by(
                    "person__last_name", "person__first_name"
                ),
            ),
        )
        .order_by("name")
    )
    return _org_payload(qs)


def single_organization_client_picker_payload(org: Organization | None) -> dict | None:
    """
    Same shape as one entry from `client_lead_contact_picker_payload`, for a single org
    (e.g. order page: department + contact only, company fixed on the proposal).
    """
    if org is None:
        return None
    o = (
        Organization.objects.filter(pk=org.pk)
        .prefetch_related(
            Prefetch("departments", queryset=Department.objects.order_by("name")),
            Prefetch(
                "memberships",
                queryset=OrganizationPerson.objects.select_related("person", "department").order_by(
                    "person__last_name", "person__first_name"
                ),
            ),
        )
        .first()
    )
    if not o:
        return None
    depts = list(o.departments.all())
    members = list(o.memberships.all())
    return {
        "uuid": str(o.uuid),
        "name": o.name,
        "departments": [{"uuid": str(d.uuid), "name": d.name} for d in depts],
        "memberships": [
            {
                "uuid": str(m.uuid),
                "label": (f"{m.person.first_name} {m.person.last_name}".strip() or str(m.person_id)),
                "department_uuid": str(m.department.uuid) if m.department_id else None,
            }
            for m in members
        ],
    }
