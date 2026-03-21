"""Resolve frontend feature access from FrontendRole / UserFrontendProfile."""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .models import UserFrontendProfile


@dataclass(frozen=True, slots=True)
class FrontendCapabilities:
    access_price_list: bool
    access_catalog: bool
    catalog_change: bool
    catalog_soft_delete: bool
    catalog_trash: bool
    catalog_purge: bool
    access_proposals: bool
    access_invoicing: bool
    access_orders: bool
    access_contacts: bool
    contacts_write: bool


_CAP_ALL_FALSE = FrontendCapabilities(
    access_price_list=False,
    access_catalog=False,
    catalog_change=False,
    catalog_soft_delete=False,
    catalog_trash=False,
    catalog_purge=False,
    access_proposals=False,
    access_invoicing=False,
    access_orders=False,
    access_contacts=False,
    contacts_write=False,
)


def _caps_from_role(role: FrontendRole) -> FrontendCapabilities:
    return FrontendCapabilities(
        access_price_list=role.access_price_list,
        access_catalog=role.access_catalog,
        catalog_change=role.catalog_change,
        catalog_soft_delete=role.catalog_soft_delete,
        catalog_trash=role.catalog_trash,
        catalog_purge=role.catalog_purge,
        access_proposals=role.access_proposals,
        access_invoicing=role.access_invoicing,
        access_orders=role.access_orders,
        access_contacts=role.access_contacts,
        contacts_write=role.contacts_write,
    )


def _legacy_full_access() -> FrontendCapabilities:
    """Superuser / explicit full template: every frontend capability on."""
    return FrontendCapabilities(
        access_price_list=True,
        access_catalog=True,
        catalog_change=True,
        catalog_soft_delete=True,
        catalog_trash=True,
        catalog_purge=True,
        access_proposals=True,
        access_invoicing=True,
        access_orders=True,
        access_contacts=True,
        contacts_write=True,
    )


def _default_capabilities_without_profile(user) -> FrontendCapabilities:
    """Match pre-role behaviour: catalog was limited to staff; purge stayed superuser-only."""
    staff = getattr(user, "is_staff", False)
    sup = getattr(user, "is_superuser", False)
    return FrontendCapabilities(
        access_price_list=True,
        access_catalog=staff,
        catalog_change=staff,
        catalog_soft_delete=staff,
        catalog_trash=staff,
        catalog_purge=sup,
        access_proposals=True,
        access_invoicing=True,
        access_orders=True,
        access_contacts=True,
        contacts_write=True,
    )


def get_capabilities(user) -> FrontendCapabilities:
    if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return _CAP_ALL_FALSE
    if user.is_superuser:
        return _legacy_full_access()
    try:
        profile = user.frontend_profile
    except UserFrontendProfile.DoesNotExist:
        return _default_capabilities_without_profile(user)
    return _caps_from_role(profile.role)


def require_capability(attribute: str):
    """View decorator: PermissionDenied if the named capability is false."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            cap = get_capabilities(request.user)
            if not getattr(cap, attribute, False):
                raise PermissionDenied(_("You do not have access to this area."))
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def require_contacts_write(view_func):
    """Require CRM write access (create/edit/delete flows)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        cap = get_capabilities(request.user)
        if not cap.access_contacts or not cap.contacts_write:
            raise PermissionDenied(_("You do not have permission to change contacts."))
        return view_func(request, *args, **kwargs)

    return _wrapped
