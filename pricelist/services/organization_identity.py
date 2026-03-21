"""Normalize and duplicate-check organization VAT / Chamber of Commerce numbers."""

from __future__ import annotations

import uuid
from typing import Any

from ..models import Organization


def normalize_vat(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return s.upper() if s else ""


def normalize_coc(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def vat_is_duplicate(vat_normalized: str, *, exclude_pk: int | None = None) -> bool:
    if not vat_normalized:
        return False
    qs = Organization.objects.filter(vat_number__iexact=vat_normalized)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def coc_is_duplicate(coc_normalized: str, *, exclude_pk: int | None = None) -> bool:
    if not coc_normalized:
        return False
    qs = Organization.objects.filter(coc_number=coc_normalized)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def resolve_exclude_pk(exclude_organization_uuid: str | None) -> int | None:
    if not exclude_organization_uuid:
        return None
    try:
        u = uuid.UUID(str(exclude_organization_uuid).strip())
    except ValueError:
        return None
    row = Organization.objects.filter(uuid=u).values_list("pk", flat=True).first()
    return int(row) if row is not None else None


def identity_check_payload(
    *,
    vat: str | None,
    coc: str | None,
    exclude_organization_uuid: str | None = None,
) -> dict[str, bool]:
    """Return flags for live duplicate check (JSON API)."""
    exclude_pk = resolve_exclude_pk(exclude_organization_uuid)
    v = normalize_vat(vat)
    c = normalize_coc(coc)
    return {
        "vat_duplicate": vat_is_duplicate(v, exclude_pk=exclude_pk),
        "coc_duplicate": coc_is_duplicate(c, exclude_pk=exclude_pk),
    }
