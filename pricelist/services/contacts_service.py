"""Query helpers and context builders for Contacts (CRM) views."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Prefetch

from ..models import Department, Organization, OrganizationPerson, OrganizationRole, Person


def _org_queryset_base():
    return Organization.objects.all().order_by("name")


def organizations_with_role(role_code: str):
    """Organizations that have the given role assignment (distinct, prefetch for list/detail cards)."""
    return (
        _org_queryset_base()
        .filter(role_assignments__role=role_code)
        .distinct()
        .prefetch_related(
            Prefetch("departments", queryset=Department.objects.order_by("name")),
            Prefetch(
                "memberships",
                queryset=OrganizationPerson.objects.select_related("person", "department").order_by(
                    "-is_primary_contact", "person__last_name", "person__first_name"
                ),
            ),
            Prefetch("role_assignments", queryset=OrganizationRole.objects.order_by("role")),
        )
    )


def build_org_chart(departments_display: list[Department], memberships: list[OrganizationPerson]) -> dict:
    """
    Company → departments → people. Memberships without a department appear under 'Unassigned'.
    Used for supplier / client / lead organization detail.
    """
    by_dept_pk: dict = defaultdict(list)
    for m in memberships:
        by_dept_pk[m.department_id].append(m)
    branches = [{"department": d, "members": by_dept_pk.get(d.pk, [])} for d in departments_display]
    unassigned = by_dept_pk.get(None, [])
    column_count = len(branches) + (1 if unassigned else 0)
    # Percent inset for horizontal connector (centers of first/last column), CSS left/right.
    hbar_inset_percent = (100.0 / (2 * column_count)) if column_count >= 2 else None
    return {
        "branches": branches,
        "unassigned": unassigned,
        "column_count": column_count,
        "hbar_inset_percent": hbar_inset_percent,
    }


def sort_departments_customer_support_first(departments: list[Department]) -> list[Department]:
    """Put departments whose name suggests customer support first (for supplier view)."""
    support = []
    other = []
    for d in departments:
        name = (d.name or "").lower()
        if "support" in name or "customer" in name or "service" in name:
            support.append(d)
        else:
            other.append(d)
    support.sort(key=lambda x: (x.name or "").lower())
    other.sort(key=lambda x: (x.name or "").lower())
    return support + other


def organization_detail_bundle(organization: Organization, *, variant: str) -> dict:
    """Context for organization detail page (shared across supplier/client/lead/network)."""
    departments = list(organization.departments.all())
    memberships = list(
        organization.memberships.select_related("person", "department").order_by(
            "-is_primary_contact", "person__last_name", "person__first_name"
        )
    )
    role_assignments = list(organization.role_assignments.all())
    role_codes = [r.role for r in role_assignments]
    departments_display = sort_departments_customer_support_first(departments)
    show_org_chart = variant in ("suppliers", "clients", "leads")
    org_chart = build_org_chart(departments_display, memberships) if show_org_chart else None
    network_out = list(
        organization.network_partner_links.select_related("linked_organization").order_by(
            "linked_organization__name"
        )
    )
    network_in = list(
        organization.counterparty_network_links.select_related("network_organization").order_by(
            "network_organization__name"
        )
    )
    return {
        "organization": organization,
        "variant": variant,
        "departments": departments,
        "departments_display": departments_display,
        "memberships": memberships,
        "role_assignments": role_assignments,
        "role_codes": role_codes,
        "show_org_chart": show_org_chart,
        "org_chart": org_chart,
        "network_partner_links": network_out,
        "counterparty_network_links": network_in,
    }


def persons_directory():
    return Person.objects.prefetch_related("memberships").order_by("last_name", "first_name")


def person_detail_bundle(person: Person) -> dict:
    life_events = list(person.life_events.all().order_by("-occurred_on", "-id"))
    memberships = list(
        person.memberships.select_related("organization", "department").order_by(
            "organization__name", "department__name"
        )
    )
    return {
        "person": person,
        "life_events": life_events,
        "memberships": memberships,
    }
