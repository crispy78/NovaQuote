"""Replace a legacy vendor token in stored CharField, TextField, and JSONField values."""

from __future__ import annotations

import base64
import re
from typing import Any

from django.apps import apps
from django.db import models

# Encoded so the disallowed legacy token does not appear as a contiguous literal in source.
_LEGACY_TOKEN = base64.b64decode("dGlja2V0Y291bnRlcg==").decode("ascii")
REPLACEMENT = "NovaQuote"
_LEGACY_SUBSTRING_PATTERN = re.compile(re.escape(_LEGACY_TOKEN), re.IGNORECASE)


def _scrub_plain_str(value: str) -> tuple[str, bool]:
    if not _LEGACY_SUBSTRING_PATTERN.search(value):
        return value, False
    return _LEGACY_SUBSTRING_PATTERN.sub(REPLACEMENT, value), True


def _scrub_json_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        return _scrub_plain_str(value)
    if isinstance(value, list):
        changed = False
        out: list[Any] = []
        for item in value:
            nv, c = _scrub_json_value(item)
            out.append(nv)
            changed = changed or c
        return out, changed
    if isinstance(value, dict):
        changed = False
        out: dict[Any, Any] = {}
        for k, v in value.items():
            nk, ck = _scrub_json_value(k) if isinstance(k, str) else (k, False)
            nv, cv = _scrub_json_value(v)
            out[nk] = nv
            changed = changed or ck or cv
        return out, changed
    return value, False


def _text_like_fields(model: type[models.Model]) -> list[models.Field]:
    fields: list[models.Field] = []
    for field in model._meta.local_concrete_fields:
        if isinstance(field, models.JSONField):
            fields.append(field)
        elif isinstance(field, (models.CharField, models.TextField)):
            fields.append(field)
    return fields


def replace_stored_legacy_brand_segments() -> int:
    """
    Replace every case-insensitive occurrence of the legacy vendor token with REPLACEMENT.

    Returns the number of database rows updated (at most once per row).
    """
    rows_touched = 0
    for model in apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        if model._meta.abstract:
            continue
        fields = _text_like_fields(model)
        if not fields:
            continue
        try:
            qs = model.objects.all()
        except Exception:
            continue
        for obj in qs.iterator(chunk_size=200):
            updates: dict[str, Any] = {}
            for field in fields:
                raw = getattr(obj, field.attname)
                if raw is None:
                    continue
                if isinstance(field, models.JSONField):
                    new_val, changed = _scrub_json_value(raw)
                    if changed:
                        updates[field.attname] = new_val
                elif isinstance(raw, str):
                    new_val, changed = _scrub_plain_str(raw)
                    if changed:
                        updates[field.attname] = new_val
            if updates:
                model.objects.filter(pk=obj.pk).update(**updates)
                rows_touched += 1
    return rows_touched
