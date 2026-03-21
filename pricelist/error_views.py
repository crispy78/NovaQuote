"""HTTP error handlers for the project URLconf."""

from __future__ import annotations

from django.http import HttpResponseForbidden
from django.template import loader


def permission_denied(request, exception=None):
    """Friendly 403 for PermissionDenied (RBAC and similar)."""
    template = loader.get_template("403.html")
    return HttpResponseForbidden(template.render({"exception": exception}, request))
