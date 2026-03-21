"""
Middleware for NovaQuote.

- FrontendAccessMiddleware: attach request.frontend_capabilities from UserFrontendProfile / role.
- LanguageFromSettingsMiddleware: frontend language from GeneralSettings (non-admin).
- LoginRequiredMiddleware: require authentication for all site URLs except admin, auth, static.
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils import translation

from .frontend_access import get_capabilities


class FrontendAccessMiddleware:
    """Set request.frontend_capabilities for templates and views (anonymous → all false)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.frontend_capabilities = get_capabilities(getattr(request, "user", None))
        return self.get_response(request)


class LoginRequiredMiddleware:
    """
    Require an authenticated user for every request outside exempt URL prefixes.

    Exempt: Django admin, auth views (login/logout/password reset), collected static files.
    Place after AuthenticationMiddleware. Does not apply to /media/ (see DEPLOYMENT.md).
    """

    EXEMPT_PREFIXES = (
        "/admin/",
        "/accounts/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            return self.get_response(request)
        return redirect_to_login(request.get_full_path())


class LanguageFromSettingsMiddleware:
    """
    Activate the language code stored in GeneralSettings.language for the request.
    Must run after SessionMiddleware. Falls back to 'en' if not set or on import error.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        if path.startswith("/admin/"):
            return self.get_response(request)
        try:
            from .models import get_general_settings

            settings_obj = get_general_settings()
            settings_obj.refresh_from_db()
            lang = (getattr(settings_obj, "language", None) or "en").strip().lower()
            if lang in ("en", "nl"):
                translation.activate(lang)
                request.LANGUAGE_CODE = lang
                if hasattr(request, "session"):
                    request.session["django_language"] = lang
            else:
                translation.activate("en")
                request.LANGUAGE_CODE = "en"
        except Exception:
            translation.activate("en")
            request.LANGUAGE_CODE = "en"
        response = self.get_response(request)
        return response
