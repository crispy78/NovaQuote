"""
Ensure FrontendRole templates and optional RBAC demo users (sales, catalog, buyer).

Used by ``seed_demo`` (after flush) and by ``seed_rbac_demo_users`` (non-destructive).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

from pricelist.models import FrontendRole, UserFrontendProfile

User = get_user_model()

DEMO_USER_SPECS: tuple[tuple[str, str], ...] = (
    ("sales", FrontendRole.SLUG_SALES),
    ("catalog", FrontendRole.SLUG_CATALOG_MANAGER),
    ("buyer", FrontendRole.SLUG_PROCUREMENT),
)


def ensure_frontend_roles() -> dict[str, FrontendRole]:
    """Create or update the four template roles; return slug -> role."""
    admin_role, _ = FrontendRole.objects.update_or_create(
        slug=FrontendRole.SLUG_ADMINISTRATOR,
        defaults={
            "name": "Administrator",
            "sort_order": 0,
            "description": "Full frontend access, including permanent catalog delete.",
            "access_price_list": True,
            "access_catalog": True,
            "catalog_change": True,
            "catalog_soft_delete": True,
            "catalog_trash": True,
            "catalog_purge": True,
            "access_proposals": True,
            "access_invoicing": True,
            "access_orders": True,
            "access_contacts": True,
            "contacts_write": True,
        },
    )
    sales_role, _ = FrontendRole.objects.update_or_create(
        slug=FrontendRole.SLUG_SALES,
        defaults={
            "name": "Sales",
            "sort_order": 10,
            "description": "Quotes, invoices, orders, and CRM. No catalog management.",
            "access_price_list": True,
            "access_catalog": False,
            "catalog_change": False,
            "catalog_soft_delete": False,
            "catalog_trash": False,
            "catalog_purge": False,
            "access_proposals": True,
            "access_invoicing": True,
            "access_orders": True,
            "access_contacts": True,
            "contacts_write": True,
        },
    )
    catalog_role, _ = FrontendRole.objects.update_or_create(
        slug=FrontendRole.SLUG_CATALOG_MANAGER,
        defaults={
            "name": "Catalog manager",
            "sort_order": 20,
            "description": "Price list and catalog only; soft-delete and restore, not permanent delete.",
            "access_price_list": True,
            "access_catalog": True,
            "catalog_change": True,
            "catalog_soft_delete": True,
            "catalog_trash": True,
            "catalog_purge": False,
            "access_proposals": False,
            "access_invoicing": False,
            "access_orders": False,
            "access_contacts": False,
            "contacts_write": False,
        },
    )
    proc_role, _ = FrontendRole.objects.update_or_create(
        slug=FrontendRole.SLUG_PROCUREMENT,
        defaults={
            "name": "Procurement",
            "sort_order": 30,
            "description": "Price list, purchase orders, and read-only contacts.",
            "access_price_list": True,
            "access_catalog": False,
            "catalog_change": False,
            "catalog_soft_delete": False,
            "catalog_trash": False,
            "catalog_purge": False,
            "access_proposals": False,
            "access_invoicing": False,
            "access_orders": True,
            "access_contacts": True,
            "contacts_write": False,
        },
    )
    return {
        FrontendRole.SLUG_ADMINISTRATOR: admin_role,
        FrontendRole.SLUG_SALES: sales_role,
        FrontendRole.SLUG_CATALOG_MANAGER: catalog_role,
        FrontendRole.SLUG_PROCUREMENT: proc_role,
    }


def ensure_frontend_roles_and_demo_users(
    demo_password: str,
    *,
    admin_user: AbstractBaseUser | None = None,
    reset_demo_passwords: bool = False,
) -> None:
    """
    Ensure roles exist, assign Administrator profile to ``admin_user`` if given,
    and create or update demo users ``sales``, ``catalog``, ``buyer``.

    New users get ``demo_password``. Existing demo users only get a new password
    when ``reset_demo_passwords`` is True.
    """
    roles = ensure_frontend_roles()
    admin_role = roles[FrontendRole.SLUG_ADMINISTRATOR]
    if admin_user is not None:
        UserFrontendProfile.objects.update_or_create(user=admin_user, defaults={"role": admin_role})

    for username, role_slug in DEMO_USER_SPECS:
        role = roles[role_slug]
        u, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@demo.local",
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        if created or reset_demo_passwords:
            u.set_password(demo_password)
        if u.email != f"{username}@demo.local":
            u.email = f"{username}@demo.local"
        u.is_active = True
        if created:
            u.is_staff = False
            u.is_superuser = False
        u.save()
        UserFrontendProfile.objects.update_or_create(user=u, defaults={"role": role})
