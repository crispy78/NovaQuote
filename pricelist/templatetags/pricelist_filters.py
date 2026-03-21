from urllib.parse import quote

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from pricelist.models import (
    format_number_with_separators,
    get_general_settings,
    price_decimal_places,
    round_price,
)

register = template.Library()


@register.filter
def nc_filesize(num_bytes):
    """Human-readable file size for catalog image list."""
    if num_bytes is None:
        return "—"
    try:
        n = int(num_bytes)
    except (TypeError, ValueError):
        return "—"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _tel_href(phone: str) -> str:
    """Build a tel: URI; keep leading + and digits."""
    if not phone:
        return ""
    raw = str(phone).strip()
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    if not cleaned:
        cleaned = "".join(c for c in raw if c.isdigit())
    if not cleaned:
        return ""
    return "tel:" + quote(cleaned, safe="+")


@register.filter(needs_autoescape=True)
def contact_mailto(value, autoescape=True):
    """
    Render an email as a mailto: link, or an em dash when empty.
    Use on organization/person views so the OS mail client opens.
    """
    if value is None:
        return mark_safe('<span class="text-slate-400">—</span>')
    raw = str(value).strip()
    if not raw:
        return mark_safe('<span class="text-slate-400">—</span>')
    href = "mailto:" + quote(raw, safe=":@._+-")
    label = conditional_escape(raw) if autoescape else raw
    return mark_safe(
        f'<a href="{href}" class="text-[var(--brand)] hover:underline break-all">{label}</a>'
    )


@register.filter(needs_autoescape=True)
def contact_tel(value, autoescape=True):
    """
    Render a phone number as a tel: link, or plain text / em dash when empty or invalid.
    """
    if value is None:
        return mark_safe('<span class="text-slate-400">—</span>')
    raw = str(value).strip()
    if not raw:
        return mark_safe('<span class="text-slate-400">—</span>')
    href = _tel_href(raw)
    label = conditional_escape(raw) if autoescape else raw
    if not href:
        return mark_safe(f'<span class="text-slate-800">{label}</span>')
    return mark_safe(
        f'<a href="{href}" class="text-[var(--brand)] hover:underline whitespace-nowrap">{label}</a>'
    )


@register.filter
def price_for_js(value, settings):
    """
    Return rounded price as string with dot decimal for use in HTML data attributes / JS.
    E.g. 1234.56 -> "1234.56". Use with format_price for display.
    """
    if value is None:
        return "0"
    if settings is None:
        settings = get_general_settings()
    rounding = getattr(settings, "rounding", "0.01") or "0.01"
    rounded = round_price(value, rounding)
    if rounded is None:
        return "0"
    return str(rounded)


@register.filter
def round_price_filter(value, rounding_str):
    """Round an amount according to the given rounding syntax. Returns Decimal or None."""
    if value is None:
        return None
    return round_price(value, rounding_str)


@register.filter
def format_price(value, settings):
    """
    Format an amount with currency, rounding and separators from GeneralSettings.
    settings: GeneralSettings instance. Returns e.g. 'EUR 1,000.00' or '€ 10,99'.
    """
    if value is None:
        return ""
    if settings is None:
        settings = get_general_settings()
    rounding = getattr(settings, "rounding", "0.01") or "0.01"
    rounded = round_price(value, rounding)
    if rounded is None:
        return ""
    currency = (getattr(settings, "currency", None) or "EUR").strip()
    dec = price_decimal_places(rounding)
    decimal_sep = getattr(settings, "decimal_sep", None)
    thousands_sep = getattr(settings, "thousands_sep", None)
    if callable(decimal_sep):
        decimal_sep = decimal_sep()
    if callable(thousands_sep):
        thousands_sep = thousands_sep()
    if decimal_sep is None:
        decimal_sep = ","
    if thousands_sep is None:
        thousands_sep = "."
    formatted = format_number_with_separators(rounded, dec, decimal_sep, thousands_sep)
    return mark_safe(f"{currency} {formatted}".strip())


@register.filter
def option_label(combination_item, option):
    """
    Return the display name for an option within a combination item (short description or brand+type).
    Usage: {{ item|option_label:option }}
    """
    if not combination_item or not option:
        return ""
    for r in combination_item.product.option_lines.all():
        if r.option_product_id == option.pk:
            return r.short_description.strip() or f"{option.brand or ''} {option.model_type or ''}".strip()
    return f"{option.brand or ''} {option.model_type or ''}".strip()


# Backward compatibility: old Dutch filter names (deprecated)
@register.filter
def afrond_prijs(value, afronding_str):
    """Deprecated: use round_price_filter."""
    return round_price_filter(value, afronding_str)


@register.filter
def format_prijs(value, settings):
    """Deprecated: use format_price."""
    return format_price(value, settings)


@register.filter
def optie_label(combinatie_item, optie):
    """Deprecated: use option_label."""
    return option_label(combinatie_item, optie)
