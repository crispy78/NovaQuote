"""Context processors for pricelist app."""

from django.templatetags.static import static

from .models import Category, get_general_settings

# Bundled default when GeneralSettings.logo is empty (replaceable in admin → General settings).
DEFAULT_SITE_LOGO_STATIC = "pricelist/img/novaquote-logo.png"


def nav_categories(request):
    """Add categories for the main nav dropdown (Products per category)."""
    return {"nav_categories": Category.objects.order_by("sort_order", "name")}


def frontend_capabilities(request):
    """Expose resolved FrontendCapabilities (see FrontendAccessMiddleware)."""
    from .frontend_access import get_capabilities

    cap = getattr(request, "frontend_capabilities", None)
    if cap is None:
        cap = get_capabilities(getattr(request, "user", None))
    return {"frontend_capabilities": cap}


def general_settings(request):
    """Expose GeneralSettings (e.g. for configurable logo) in all templates."""
    gs = get_general_settings()
    logo_url = gs.logo.url if gs.logo else static(DEFAULT_SITE_LOGO_STATIC)
    return {
        "general_settings": gs,
        "general_settings_logo_url": logo_url,
    }
