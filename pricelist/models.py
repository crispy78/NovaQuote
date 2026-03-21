from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class Supplier(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        db_table = "catalogus_supplier"
        verbose_name = _("Supplier")
        verbose_name_plural = _("Suppliers")

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    name = models.CharField(max_length=255, unique=True)
    sort_order = models.PositiveIntegerField(default=0, help_text=_("Optional: use this to sort categories."))

    class Meta:
        db_table = "catalogus_category"
        ordering = ("sort_order", "name")
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    def __str__(self) -> str:
        return self.name


def _parse_rounding(rounding_str):
    """
    Parse rounding syntax. Returns (round_to: Decimal, subtract: Decimal) or None on invalid syntax.
    """
    if not rounding_str or not str(rounding_str).strip():
        return Decimal("0.01"), Decimal("0")
    s = str(rounding_str).strip().replace(",", ".")
    if "-" in s:
        parts = s.split("-", 1)
        try:
            round_to = Decimal(parts[0].strip())
            subtract = Decimal(parts[1].strip())
            if round_to <= 0 or subtract < 0:
                return None
            return round_to, subtract
        except Exception:
            return None
    try:
        round_to = Decimal(s)
        if round_to <= 0:
            return None
        return round_to, Decimal("0")
    except Exception:
        return None


def round_price(value, rounding_str):
    """Apply rounding to an amount. Returns rounded Decimal, or value unchanged if parsing fails."""
    from decimal import ROUND_HALF_UP

    if value is None:
        return None
    value = Decimal(str(value))
    parsed = _parse_rounding(rounding_str)
    if not parsed:
        return value
    round_to, subtract = parsed
    if round_to <= 0:
        return value
    rounded = (value / round_to).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * round_to - subtract
    return rounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_hex_color(s):
    """Return True if s looks like a hex colour (#rgb or #rrggbb)."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if not s.startswith("#") or len(s) not in (4, 7):
        return False
    try:
        int(s[1:], 16)
        return True
    except ValueError:
        return False


def _hex_to_rgb_triplet(hex_str):
    """Return (r, g, b) for #rgb / #rrggbb, or None."""
    s = (hex_str or "").strip()
    if not s.startswith("#"):
        return None
    h = s[1:]
    try:
        if len(h) == 3:
            r, g, b = (int(c * 2, 16) for c in h)
        elif len(h) == 6:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        else:
            return None
        return r, g, b
    except ValueError:
        return None


def _darken_hex(hex_str, factor):
    """Return a darker hex colour by multiplying RGB by factor (0–1)."""
    hex_str = (hex_str or "#008080").strip()
    if not hex_str.startswith("#") or len(hex_str) not in (4, 7):
        return "#006666"
    try:
        h = hex_str[1:]
        if len(h) == 3:
            r, g, b = (int(c * 2, 16) for c in h)
        else:
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, TypeError):
        return "#006666"


def price_decimal_places(rounding_str):
    """Determine number of decimal places for display."""
    parsed = _parse_rounding(rounding_str)
    if not parsed:
        return 2
    round_to, subtract = parsed
    if subtract != 0:
        return 2
    if round_to >= 1:
        return 2
    s = str(round_to)
    if "." in s:
        return len(s.split(".")[-1].rstrip("0"))
    return 2


def format_number_with_separators(value, decimal_places, decimal_sep, thousands_sep):
    """Format a number with the given decimal places and separators."""
    if value is None:
        return ""
    d = Decimal(str(value))
    int_part = int(d)
    int_str = str(abs(int_part))
    if thousands_sep:
        grouped = []
        for i, c in enumerate(reversed(int_str)):
            if i and i % 3 == 0:
                grouped.append(thousands_sep)
            grouped.append(c)
        int_str = "".join(reversed(grouped))
    if int_part < 0:
        int_str = "-" + int_str
    if decimal_places <= 0:
        return int_str
    remainder = abs(d) - int(abs(d))
    frac_int = int(round(remainder * (10 ** decimal_places)))
    frac_str = str(frac_int).zfill(decimal_places)
    return int_str + decimal_sep + frac_str


class GeneralSettings(models.Model):
    """General settings (singleton). Currency, rounding, number format."""
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for the settings record (mostly for integrations/tests)."),
    )
    NUMBER_FORMAT_EUROPE = "eu"
    NUMBER_FORMAT_US = "us"
    NUMBER_FORMAT_CHOICES = [
        (NUMBER_FORMAT_EUROPE, _("Europe (period for thousands, comma for decimals: 1.000,00)")),
        (NUMBER_FORMAT_US, _("US (comma for thousands, period for decimals: 1,000.00)")),
    ]

    currency = models.CharField(
        max_length=32,
        default="EUR",
        verbose_name=_("Currency"),
        help_text=_("Currency code or symbol for display, e.g. EUR or €."),
    )
    rounding = models.CharField(
        max_length=64,
        default="0.01",
        verbose_name=_("Rounding"),
        help_text=_("Rounding syntax: number = round to that amount (0.01, 0.05, 0.10, 0.50, 1, 5, 10, …). Option: number-minus (e.g. 1-0.01) = round to whole units then subtract."),
    )
    number_format = models.CharField(
        max_length=8,
        choices=NUMBER_FORMAT_CHOICES,
        default=NUMBER_FORMAT_EUROPE,
        verbose_name=_("Number format"),
        help_text=_("Separators: Europe = 1.000,00 ; US = 1,000.00"),
    )
    minimum_margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Minimum margin %"),
        help_text=_("Minimum margin % for combinations (e.g. 20 = at least 20% margin). At 0 no check is performed."),
    )
    show_price_history_chart_on_product_page = models.BooleanField(
        default=False,
        verbose_name=_("Show price history chart on product page"),
        help_text=_("Show a price history chart on the product page."),
    )
    show_cost_in_price_history_chart = models.BooleanField(
        default=True,
        verbose_name=_("Cost price in price history chart"),
        help_text=_("Show cost price in the price history chart on the product page."),
    )
    show_sales_in_price_history_chart = models.BooleanField(
        default=False,
        verbose_name=_("Sales price in price history chart"),
        help_text=_("Show sales price (from cost + profit profile) in the price history chart."),
    )
    show_supplier_on_frontend = models.BooleanField(
        default=True,
        verbose_name=_("Show supplier on frontend"),
        help_text=_("Show the supplier on the price list and product page."),
    )
    show_category_on_frontend = models.BooleanField(
        default=True,
        verbose_name=_("Show category on frontend"),
        help_text=_("Show the category on the price list and product page."),
    )
    LANGUAGE_EN = "en"
    LANGUAGE_NL = "nl"
    LANGUAGE_CHOICES = [
        (LANGUAGE_EN, _("English")),
        (LANGUAGE_NL, _("Dutch")),
    ]
    language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default=LANGUAGE_EN,
        verbose_name=_("Language (frontend)"),
        help_text=_("Language for the price list and product page. Admin keeps browser/system language."),
    )
    # Maintenance contract calculation (used on proposal for contract options)
    time_per_product_minutes = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("15.00"),
        verbose_name=_("Time per product (minutes)"),
        help_text=_("Estimated minutes per product per maintenance visit."),
    )
    minimum_visit_minutes = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("60.00"),
        verbose_name=_("Minimum visit time (minutes)"),
        help_text=_("Minimum duration of a maintenance visit (used if calculated time is lower)."),
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("75.00"),
        verbose_name=_("Technician hourly rate"),
        help_text=_("Hourly rate for labour cost calculation."),
    )
    show_contract_fee_calculation = models.BooleanField(
        default=False,
        verbose_name=_("Show fee calculation on proposal"),
        help_text=_("When enabled, the proposal page shows the calculation breakdown (hardware fee, labour, etc.) below each contract option."),
    )
    logo = models.ImageField(
        upload_to="general",
        blank=True,
        null=True,
        verbose_name=_("Logo"),
        help_text=_(
            "Optional. Replaces the bundled NovaQuote logo in the frontend and admin header. "
            "Leave empty to use the default. Recommended: PNG or SVG, moderate height (e.g. 48px)."
        ),
    )
    site_name = models.CharField(
        max_length=255,
        default="NovaQuote",
        blank=True,
        verbose_name=_("Site name"),
        help_text=_("Title and brand name shown on the frontend (e.g. in the header and page titles)."),
    )

    COLOR_SCHEME_ORANGE = "orange"
    COLOR_SCHEME_NAVY = "navy"
    COLOR_SCHEME_TEAL = "teal"
    COLOR_SCHEME_BLACK = "black"
    COLOR_SCHEME_RED = "red"
    COLOR_SCHEME_CHOICES = [
        (COLOR_SCHEME_ORANGE, _("Orange (#FFA726)")),
        (COLOR_SCHEME_NAVY, _("Navy blue (#283593)")),
        (COLOR_SCHEME_TEAL, _("Teal (#008080)")),
        (COLOR_SCHEME_BLACK, _("Black (#424242)")),
        (COLOR_SCHEME_RED, _("Red (#DC143C)")),
    ]
    # (primary, hover) — hover is a darker companion for links/buttons on light backgrounds
    COLOR_SCHEME_PALETTES = {
        COLOR_SCHEME_ORANGE: ("#FFA726", "#F57C00"),
        COLOR_SCHEME_NAVY: ("#283593", "#1A237E"),
        COLOR_SCHEME_TEAL: ("#008080", "#006666"),
        COLOR_SCHEME_BLACK: ("#424242", "#212121"),
        COLOR_SCHEME_RED: ("#DC143C", "#AD102F"),
    }

    color_scheme = models.CharField(
        max_length=32,
        choices=COLOR_SCHEME_CHOICES,
        default=COLOR_SCHEME_TEAL,
        verbose_name=_("Color scheme"),
        help_text=_("Brand colour for buttons and links on the frontend and in admin."),
    )
    primary_color = models.CharField(
        max_length=9,
        default="#008080",
        verbose_name=_("Primary colour (legacy)"),
        help_text=_("Synced from the selected theme for compatibility; not shown in admin."),
    )
    primary_color_hover = models.CharField(
        max_length=9,
        blank=True,
        verbose_name=_("Primary colour hover"),
        help_text=_("Optional. Darker hex for hover states. Leave empty to use an automatic darker variant of the primary colour."),
    )

    class Meta:
        db_table = "catalogus_generalsettings"
        verbose_name = _("General setting")
        verbose_name_plural = _("General settings")

    def __str__(self):
        return str(_("General settings"))

    def clean(self):
        super().clean()
        if self.rounding and _parse_rounding(self.rounding) is None:
            raise ValidationError(
                {"rounding": _("Invalid syntax. Use e.g. 0.01, 0.05, 1 or 1-0.01.")}
            )
        if self.primary_color and not _is_hex_color(self.primary_color.strip()):
            raise ValidationError(
                {"primary_color": _("Enter a valid hex colour.")}
            )
        if self.primary_color_hover and not _is_hex_color(self.primary_color_hover):
            raise ValidationError(
                {"primary_color_hover": _("Enter a valid hex colour or leave empty.")}
            )

    def save(self, *args, **kwargs):
        """Keep legacy primary_colour fields aligned with the selected theme."""
        palette = self.COLOR_SCHEME_PALETTES.get(self.color_scheme)
        if palette:
            self.primary_color = palette[0]
            self.primary_color_hover = palette[1]
        super().save(*args, **kwargs)

    @property
    def effective_primary_color(self) -> str:
        """Colour used for brand accents."""
        palette = self.COLOR_SCHEME_PALETTES.get(self.color_scheme)
        if palette:
            return palette[0]
        return (self.primary_color or "#008080").strip()

    @property
    def effective_primary_hover(self) -> str:
        """Hover colour for brand accents."""
        palette = self.COLOR_SCHEME_PALETTES.get(self.color_scheme)
        if palette:
            return palette[1]
        return _darken_hex(self.effective_primary_color, 0.85)

    @property
    def effective_primary_rgba_faint(self) -> str:
        """RGBA string for light chart fills matching the effective primary (~12% opacity)."""
        alpha = 0.12
        t = _hex_to_rgb_triplet(self.effective_primary_color)
        if not t:
            return f"rgba(0, 128, 128, {alpha})"
        r, g, b = t
        return f"rgba({r},{g},{b},{alpha})"

    def primary_color_hover_resolved(self):
        """Return stored hover or a darker variant of the effective primary."""
        if self.primary_color_hover and self.primary_color_hover.strip():
            return self.primary_color_hover.strip()
        return _darken_hex(self.effective_primary_color, 0.85)

    def decimal_sep(self):
        return "," if self.number_format == self.NUMBER_FORMAT_EUROPE else "."

    def thousands_sep(self):
        return "." if self.number_format == self.NUMBER_FORMAT_EUROPE else ","


def get_general_settings():
    """Return the GeneralSettings record. Creates one automatically if it does not exist."""
    inst = GeneralSettings.objects.first()
    if inst is None:
        inst = GeneralSettings.objects.create(
            currency="EUR",
            rounding="0.01",
            number_format=GeneralSettings.NUMBER_FORMAT_EUROPE,
            language=GeneralSettings.LANGUAGE_EN,
            color_scheme=GeneralSettings.COLOR_SCHEME_TEAL,
            primary_color="#008080",
            primary_color_hover="#006666",
        )
    return inst


class ContractDuration(models.Model):
    """Contract duration option for maintenance contracts on the proposal (e.g. 3 years, 5 years)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier so snapshots stay linked to this contract form even if name is reused."),
    )
    name = models.CharField(
        max_length=64,
        verbose_name=_("Name"),
        help_text=_("E.g. '3 years' or '5 years'."),
    )
    duration_months = models.PositiveIntegerField(
        verbose_name=_("Duration (months)"),
        help_text=_("Contract length in months, e.g. 36 or 60."),
    )
    hardware_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_("Hardware fee (%)"),
        help_text=_("Percentage of total hardware value as fee, e.g. 10 or 7.5."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("If unchecked, this option will not appear on the proposal."),
    )
    visits_per_contract = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("6.00"),
        verbose_name=_("Visits per contract period"),
        help_text=_("Total number of maintenance visits in this contract period (e.g. 6 for 3 years, 10 for 5 years)."),
    )

    class Meta:
        db_table = "catalogus_contractduration"
        ordering = ("duration_months",)
        verbose_name = _("Contract duration")
        verbose_name_plural = _("Contract durations")

    def __str__(self):
        return self.name


def product_image_upload_to(instance, filename):
    """Store product images as product_images/<uuid>.png. All uploads are normalized to PNG."""
    return f"product_images/{uuid.uuid4().hex}.png"


# Legacy alias for migration 0011
product_afbeelding_upload_to = product_image_upload_to


def combination_image_upload_to(instance, filename):
    """Store combination images as combination_images/<uuid>.png."""
    return f"combination_images/{uuid.uuid4().hex}.png"


class ActiveCatalogQuerySet(models.QuerySet):
    """QuerySet excluding catalog rows marked removed (soft delete)."""

    def active(self):
        return self.filter(deleted_at__isnull=True)


class ActiveCatalogManager(models.Manager):
    """Default manager: only non-removed products/combinations."""

    def get_queryset(self):
        return ActiveCatalogQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class ProfitProfile(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    name = models.CharField(max_length=255, unique=True)
    markup_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text=_("Percentage markup on cost price (e.g. 30 for 30%)."),
    )
    markup_fixed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Fixed markup in euros added to the sales price."),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogus_profitprofile"
        verbose_name = _("Profit profile")
        verbose_name_plural = _("Profit profiles")
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.markup_percentage:.2f}% + € {self.markup_fixed:.2f})"


class Product(models.Model):
    brand = models.CharField(max_length=255, blank=True, help_text=_("E.g. HP, Epson."))
    model_type = models.CharField(max_length=255, blank=True, help_text=_("E.g. model name or type."))
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Deprecated; use brand + model_type instead."),
    )
    article_number = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text=_("Technical article number (UUID) for filenames and links. Unique per product."),
    )
    description = models.TextField(blank=True, verbose_name=_("Description"))
    usps = models.TextField(help_text=_("USPs, one per line"), blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        blank=True,
        null=True,
    )
    image = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    supplier_order_number = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Order/article number used by the supplier. Same article (brand/type) may appear multiple times if order number or supplier differs."),
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Not required for services with fixed fee (see Fixed sales price)."),
    )
    fixed_sales_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Fixed sales price (service)"),
        help_text=_("For services (e.g. configuration): fixed fee. Used as sales price; for margin, cost counts as 0."),
    )
    profit_profile = models.ForeignKey(
        ProfitProfile,
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
        help_text=_("Required profit profile for this product (in admin)."),
    )
    price_last_changed = models.DateField(blank=True, null=True)
    price_last_checked = models.DateField(
        blank=True,
        null=True,
        help_text=_("Date when the price was last checked."),
    )
    show_in_price_list = models.BooleanField(
        default=True,
        verbose_name=_("Show in price list"),
        help_text=_("If disabled: this product does not appear as a standalone item on the price list. It remains visible as an option on other products."),
    )
    is_margin_product = models.BooleanField(
        default=True,
        verbose_name=_("Margin product"),
        help_text=_("On by default. Turn off for services/other items: revenue counts in total but not in margin calculation; shown as 'other revenue'."),
    )
    supplier_crm_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products_supplier_crm",
        verbose_name=_("Supplier company (Contacts)"),
        help_text=_("CRM organization with the supplier role for this catalog supplier."),
    )
    supplier_crm_department = models.ForeignKey(
        "Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products_supplier_crm",
        verbose_name=_("Supplier department"),
    )
    supplier_crm_contact = models.ForeignKey(
        "OrganizationPerson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products_supplier_crm",
        verbose_name=_("Supplier contact person"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Removed at"),
        help_text=_("When set, this product is hidden from the catalog. Staff can restore or purge."),
    )

    objects = ActiveCatalogManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "catalogus_product"

    def clean(self):
        super().clean()
        org_id = self.supplier_crm_organization_id
        dept = self.supplier_crm_department_id
        contact = self.supplier_crm_contact
        if org_id:
            if not OrganizationRole.objects.filter(
                organization_id=org_id,
                role=OrganizationRole.ROLE_SUPPLIER,
            ).exists():
                raise ValidationError(
                    {
                        "supplier_crm_organization": _(
                            "Selected organization must have the Supplier role in Contacts."
                        )
                    }
                )
        if dept and org_id and self.supplier_crm_department.organization_id != org_id:
            raise ValidationError(
                {"supplier_crm_department": _("Department must belong to the selected supplier company.")}
            )
        if contact:
            if org_id and contact.organization_id != org_id:
                raise ValidationError(
                    {"supplier_crm_contact": _("Contact must belong to the selected supplier company.")}
                )
            if dept and contact.department_id and contact.department_id != dept:
                raise ValidationError(
                    {
                        "supplier_crm_contact": _(
                            "Contact’s department does not match the selected department."
                        )
                    }
                )

    @property
    def calculated_sales_price(self):
        """Sales unit price using the preferred (or only) catalog supplier row when defined."""
        if self.fixed_sales_price is not None:
            return self.fixed_sales_price
        ps = self.preferred_product_supplier()
        cost = ps.cost_price if ps is not None else self.cost_price
        if cost is None or not self.profit_profile or not self.profit_profile.is_active:
            return None
        basis = cost * (Decimal("1.0") + (self.profit_profile.markup_percentage / Decimal("100")))
        return basis + self.profit_profile.markup_fixed

    def preferred_product_supplier(self):
        """
        Preferred `ProductSupplier` row for pricing and price list (exactly one should be preferred).
        Falls back to the first row if none marked preferred.
        """
        # Use cached prefetch when available
        rows = getattr(self, "_prefetched_objects_cache", {}).get("product_suppliers")
        if rows is not None:
            for ps in rows:
                if ps.is_preferred:
                    return ps
            return rows[0] if rows else None
        ps = (
            self.product_suppliers.filter(is_preferred=True).select_related("supplier").first()
            or self.product_suppliers.select_related("supplier").order_by("sort_order", "pk").first()
        )
        return ps

    def sales_price_for_product_supplier(self, ps: "ProductSupplier") -> Decimal | None:
        """Unit sales price if this line were sourced from the given supplier row."""
        if ps is None or ps.product_id != self.pk:
            return None
        if self.fixed_sales_price is not None:
            return self.fixed_sales_price
        if ps.cost_price is None or not self.profit_profile or not self.profit_profile.is_active:
            return None
        basis = ps.cost_price * (Decimal("1.0") + (self.profit_profile.markup_percentage / Decimal("100")))
        return basis + self.profit_profile.markup_fixed

    def __str__(self) -> str:
        label = f"{self.brand or ''} {self.model_type or ''}".strip()
        return label or str(self.article_number)


class ProductSupplier(models.Model):
    """
    One purchasable offer for a catalog product: supplier, cost, lead time, payment terms.
    Exactly one row per product should have `is_preferred` (used for price list default).
    The parent `Product.supplier` / `cost_price` / `supplier_order_number` are kept in sync
    with the preferred row for backward compatibility.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for integrations and proposal line references."),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_suppliers",
        verbose_name=_("Product"),
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="product_supplier_offers",
        verbose_name=_("Supplier"),
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("Cost price"),
        help_text=_("Purchase cost from this supplier (same rules as product cost: optional for fixed-fee services)."),
    )
    supplier_order_number = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Supplier order / article number"),
    )
    lead_time_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Lead time (days)"),
        help_text=_("Typical delivery lead time for proposals sorted by “fastest”."),
    )
    payment_terms = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Payment terms (label)"),
        help_text=_("e.g. Net 30 — shown in proposal supplier picker."),
    )
    payment_terms_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Payment due (days)"),
        help_text=_("Numeric days until due (e.g. 30). Used for “best payment terms” (longer is better cashflow)."),
    )
    is_preferred = models.BooleanField(
        default=False,
        verbose_name=_("Preferred supplier"),
        help_text=_("Price list and default proposal line use this row when multiple suppliers exist."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))

    class Meta:
        db_table = "catalogus_productsupplier"
        ordering = ("product", "sort_order", "supplier__name")
        verbose_name = _("Product supplier offer")
        verbose_name_plural = _("Product supplier offers")
        constraints = [
            models.UniqueConstraint(fields=["product", "supplier"], name="uniq_product_supplier_offer"),
        ]

    def __str__(self) -> str:
        return f"{self.product} ← {self.supplier}"

    def save(self, *args, **kwargs):
        if self.is_preferred:
            ProductSupplier.objects.filter(product_id=self.product_id).exclude(pk=self.pk).update(is_preferred=False)
        super().save(*args, **kwargs)
        sync_product_primary_from_suppliers(self.product_id)

    def delete(self, *args, **kwargs):
        pid = self.product_id
        super().delete(*args, **kwargs)
        sync_product_primary_from_suppliers(pid)


def sync_product_primary_from_suppliers(product_id: int) -> None:
    """Mirror preferred ProductSupplier onto Product.supplier / cost / order number (no full Product.save())."""
    ps = (
        ProductSupplier.objects.filter(product_id=product_id, is_preferred=True)
        .select_related("supplier")
        .first()
        or ProductSupplier.objects.filter(product_id=product_id).select_related("supplier").order_by("sort_order", "pk").first()
    )
    if ps is None:
        return
    Product.objects.filter(pk=product_id).update(
        supplier_id=ps.supplier_id,
        cost_price=ps.cost_price,
        supplier_order_number=ps.supplier_order_number or "",
    )


class ProductOption(models.Model):
    """Link: main product has an option product with optional short display name."""
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and integrations."),
    )
    main_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="option_lines",
        verbose_name=_("Main product"),
    )
    option_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="as_option_for",
        verbose_name=_("Option (product)"),
    )
    short_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Short description"),
        help_text=_("Short display name for this option (e.g. 'Display', 'Cutter'). Empty = brand + type of option product."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))

    class Meta:
        db_table = "catalogus_productoption"
        ordering = ("sort_order", "option_product__brand", "option_product__model_type")
        unique_together = [("main_product", "option_product")]
        verbose_name = _("Product option")
        verbose_name_plural = _("Product options")

    def __str__(self) -> str:
        label = self.short_description.strip() or str(self.option_product)
        return f"{self.main_product} → {label}"


class PriceHistory(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and audit views."),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_history")
    previous_cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Previous cost price"))
    new_cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("New cost price"))
    change_date = models.DateField(verbose_name=_("Change date"))
    sales_price_at_date = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Sales price at date"),
        help_text=_("Sales price as it was on the change date (with the profit profile then in effect)."),
    )

    class Meta:
        db_table = "catalogus_pricehistory"
        verbose_name = _("Price history")
        verbose_name_plural = _("Price histories")

    def __str__(self) -> str:
        return f"{self.product} ({self.change_date})"


class CombinationItem(models.Model):
    """One product within a combination, with optional selected options."""
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and integrations."),
    )
    combination = models.ForeignKey(
        "Combination",
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Combination"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="combination_items",
        verbose_name=_("Product"),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    selected_options = models.ManyToManyField(
        Product,
        related_name="combination_item_options",
        blank=True,
        verbose_name=_("Selected options"),
        help_text=_("Options for this product included in the combination (must be options of this product)."),
    )

    class Meta:
        db_table = "catalogus_combinatieitem"
        ordering = ("sort_order", "id")
        verbose_name = _("Combination item")
        verbose_name_plural = _("Combination items")

    def __str__(self) -> str:
        return f"{self.combination.name}: {self.product}"

    def item_price(self):
        """Sales price of this product + selected options."""
        total = self.product.calculated_sales_price or Decimal("0.00")
        for opt in self.selected_options.all():
            p = opt.calculated_sales_price
            if p is not None:
                total += p
        return total

    def item_cost_price(self):
        """Cost price of this product + selected options. Services count as 0."""
        total = (
            Decimal("0.00")
            if self.product.fixed_sales_price is not None
            else (self.product.cost_price or Decimal("0.00"))
        )
        for opt in self.selected_options.all():
            if opt.fixed_sales_price is not None:
                continue
            if opt.cost_price is not None:
                total += opt.cost_price
        return total


class Combination(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    usps = models.TextField(blank=True, verbose_name=_("USPs"), help_text=_("USPs, one per line."))
    image = models.ImageField(
        upload_to=combination_image_upload_to,
        blank=True,
        null=True,
        verbose_name=_("Image"),
    )
    products = models.ManyToManyField(
        Product,
        related_name="combinations",
        blank=True,
        help_text=_("Deprecated: use Combination items below. Still used until migration."),
    )
    combination_sales_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Legacy field: final offer price. Filled automatically from type and discount fields."),
    )

    OFFER_TYPE_NONE = "none"
    OFFER_TYPE_FIXED_AMOUNT = "fixed_amount"
    OFFER_TYPE_DISCOUNT_AMOUNT = "discount_amount"
    OFFER_TYPE_DISCOUNT_PERCENTAGE = "discount_percentage"

    OFFER_TYPE_CHOICES = [
        (OFFER_TYPE_NONE, _("No offer (set at regular prices)")),
        (OFFER_TYPE_FIXED_AMOUNT, _("Fixed amount (offer price)")),
        (OFFER_TYPE_DISCOUNT_AMOUNT, _("Discount amount")),
        (OFFER_TYPE_DISCOUNT_PERCENTAGE, _("Discount percentage")),
    ]

    offer_type = models.CharField(
        max_length=32,
        choices=OFFER_TYPE_CHOICES,
        default=OFFER_TYPE_DISCOUNT_AMOUNT,
        help_text=_("How the combination price is determined."),
    )
    offer_fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Price for the margin-products part. Other revenue (services etc.) is added to this."),
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Fixed discount amount on the total of margin products (not on other revenue)."),
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Discount percentage on the total of margin products (not on other revenue). E.g. 10 = 10%."),
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Removed at"),
        help_text=_("When set, this combination is hidden from the catalog. Staff can restore or purge."),
    )

    objects = ActiveCatalogManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "catalogus_combinatie"
        verbose_name = _("Combination")
        verbose_name_plural = _("Combinations")

    @property
    def original_price(self):
        if self.items.exists():
            return sum((item.item_price() for item in self.items.all()), Decimal("0.00"))
        total = Decimal("0.00")
        for product in self.products.all():
            p = product.calculated_sales_price
            if p is not None:
                total += p
        return total

    @property
    def total_cost_price(self):
        """Total cost price of all products (+ selected options) in the combination."""
        if self.items.exists():
            return sum((item.item_cost_price() for item in self.items.all()), Decimal("0.00"))
        total = Decimal("0.00")
        for product in self.products.all():
            if product.fixed_sales_price is not None:
                continue
            if product.cost_price is not None:
                total += product.cost_price
        return total

    @property
    def sales_margin_products(self):
        """Sales value of parts that count as margin product."""
        if not self.items.exists():
            total = Decimal("0.00")
            for product in self.products.all():
                if product.is_margin_product and product.calculated_sales_price is not None:
                    total += product.calculated_sales_price
            return total
        total = Decimal("0.00")
        for item in self.items.select_related("product").prefetch_related("selected_options"):
            if item.product.is_margin_product:
                p = item.product.calculated_sales_price
                if p is not None:
                    total += p
            for opt in item.selected_options.all():
                if opt.is_margin_product:
                    p = opt.calculated_sales_price
                    if p is not None:
                        total += p
        return total

    @property
    def cost_margin_products(self):
        """Cost of parts that count as margin product."""
        if not self.items.exists():
            total = Decimal("0.00")
            for product in self.products.all():
                if not product.is_margin_product:
                    continue
                if product.fixed_sales_price is not None:
                    continue
                if product.cost_price is not None:
                    total += product.cost_price
            return total
        total = Decimal("0.00")
        for item in self.items.select_related("product").prefetch_related("selected_options"):
            if item.product.is_margin_product and item.product.fixed_sales_price is None and item.product.cost_price is not None:
                total += item.product.cost_price
            for opt in item.selected_options.all():
                if opt.is_margin_product and opt.fixed_sales_price is None and opt.cost_price is not None:
                    total += opt.cost_price
        return total

    @property
    def other_revenue(self):
        """Revenue from parts that are not margin products (services etc.)."""
        return (self.original_price or Decimal("0.00")) - self.sales_margin_products

    @property
    def offer_price(self):
        """Offer price = [price for margin products after discount] + other revenue."""
        marge_part = self.sales_margin_products
        other = self.other_revenue

        if self.offer_type == self.OFFER_TYPE_NONE:
            return marge_part + other

        if self.offer_type == self.OFFER_TYPE_FIXED_AMOUNT and self.offer_fixed_amount is not None:
            return self.offer_fixed_amount + other

        if self.offer_type == self.OFFER_TYPE_DISCOUNT_AMOUNT and self.discount_amount is not None:
            price_margin = max(marge_part - self.discount_amount, Decimal("0.00"))
            return price_margin + other

        if self.offer_type == self.OFFER_TYPE_DISCOUNT_PERCENTAGE and self.discount_percentage is not None:
            factor = Decimal("1.00") - (self.discount_percentage / Decimal("100"))
            if factor < Decimal("0.00"):
                factor = Decimal("0.00")
            price_margin = (marge_part * factor).quantize(Decimal("0.01"))
            return price_margin + other

        if self.combination_sales_price is not None:
            return self.combination_sales_price
        return marge_part + other

    @property
    def margin_percentage(self):
        """Margin over margin products after discount."""
        cost_margin = self.cost_margin_products
        if cost_margin <= 0:
            return None
        offer = self.offer_price
        if offer is None:
            return None
        margin_part_after_discount = offer - self.other_revenue
        if margin_part_after_discount < 0:
            margin_part_after_discount = Decimal("0.00")
        return (margin_part_after_discount - cost_margin) / cost_margin * Decimal("100")

    @property
    def margin_below_minimum(self):
        from .models import get_general_settings

        gen_settings = get_general_settings()
        threshold = getattr(gen_settings, "minimum_margin_percentage", None)
        marge = self.margin_percentage
        if marge is None or threshold is None:
            return False
        try:
            return marge < Decimal(str(threshold))
        except Exception:
            return False

    @property
    def date_range(self):
        if self.items.exists():
            pks = set()
            for item in self.items.select_related("product").prefetch_related("selected_options"):
                pks.add(item.product_id)
                for opt in item.selected_options.all():
                    pks.add(opt.pk)
            qs = Product.objects.filter(pk__in=pks).exclude(
                price_last_changed__isnull=True
            ).values_list("price_last_changed", flat=True)
        else:
            qs = self.products.exclude(price_last_changed__isnull=True).values_list(
                "price_last_changed", flat=True
            )
        dates = list(qs)
        if not dates:
            return None
        oldest = min(dates)
        newest = max(dates)
        return f"{oldest.strftime('%d-%m-%Y')} / {newest.strftime('%d-%m-%Y')}"

    def __str__(self) -> str:
        return self.name


class Proposal(models.Model):
    """Saved calculation (offerte) with snapshot of lines and prices at save time."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for URLs; proposal is reachable via /proposal/saved/<uuid>/ or by reference."),
    )
    reference = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Reference"),
        help_text=_("Optional reference or name for this calculation."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_proposals",
        verbose_name=_("Created by"),
    )
    # Maintenance calculation at save time (so the full proposal is frozen in time)
    time_per_product_snapshot = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Time per product (minutes) at save"),
    )
    minimum_visit_snapshot = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Minimum visit time (minutes) at save"),
    )
    hourly_rate_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Hourly rate at save"),
    )
    client_crm_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposals_client_crm",
        verbose_name=_("Client / lead company (Contacts)"),
        help_text=_("CRM organization with the client or lead role for this proposal."),
    )
    client_crm_department = models.ForeignKey(
        "Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposals_client_crm",
        verbose_name=_("Client department"),
    )
    client_crm_contact = models.ForeignKey(
        "OrganizationPerson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposals_client_crm",
        verbose_name=_("Client contact person"),
    )

    class Meta:
        db_table = "catalogus_proposal"
        ordering = ("-updated_at",)
        verbose_name = _("Saved proposal")
        verbose_name_plural = _("Saved proposals")

    def clean(self):
        super().clean()
        org_id = self.client_crm_organization_id
        dept = self.client_crm_department_id
        contact = self.client_crm_contact
        client_lead_roles = (OrganizationRole.ROLE_CLIENT, OrganizationRole.ROLE_LEAD)
        if org_id:
            role_codes = set(
                OrganizationRole.objects.filter(organization_id=org_id).values_list("role", flat=True)
            )
            if not role_codes.intersection(set(client_lead_roles)):
                raise ValidationError(
                    {
                        "client_crm_organization": _(
                            "Selected organization must have the Client or Lead role in Contacts."
                        )
                    }
                )
        if dept and org_id and self.client_crm_department.organization_id != org_id:
            raise ValidationError(
                {"client_crm_department": _("Department must belong to the selected company.")}
            )
        if contact:
            if org_id and contact.organization_id != org_id:
                raise ValidationError(
                    {"client_crm_contact": _("Contact must belong to the selected company.")}
                )
            if dept and contact.department_id and contact.department_id != dept:
                raise ValidationError(
                    {
                        "client_crm_contact": _(
                            "Contact’s department does not match the selected department."
                        )
                    }
                )

    def __str__(self) -> str:
        """Include UUID so admin/autocomplete shows the stable id, not only the numeric PK."""
        label = (self.reference or "").strip() or str(self.uuid)
        return f"{label} ({self.uuid})"

    def grand_total_snapshot(self):
        """Sum of line totals (from snapshot)."""
        return self.lines.aggregate(total=models.Sum("line_total_snapshot"))["total"] or Decimal("0.00")


class ProposalLine(models.Model):
    """One line in a saved proposal: product or combination with quantity and snapshot prices."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and stable UI anchors."),
    )

    LINE_TYPE_PRODUCT = "product"
    LINE_TYPE_COMBINATION = "combination"
    LINE_TYPE_CHOICES = [
        (LINE_TYPE_PRODUCT, _("Product")),
        (LINE_TYPE_COMBINATION, _("Combination")),
    ]

    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Proposal"),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    line_type = models.CharField(
        max_length=16,
        choices=LINE_TYPE_CHOICES,
        verbose_name=_("Type"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_lines",
        verbose_name=_("Product"),
    )
    combination = models.ForeignKey(
        Combination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_lines",
        verbose_name=_("Combination"),
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("1"),
        verbose_name=_("Quantity"),
    )
    unit_price_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Unit price (at save)"),
    )
    line_total_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Line total (at save)"),
    )
    name_snapshot = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Name (at save)"),
        help_text=_("Stored name for display when product/combination is later removed."),
    )
    is_removed = models.BooleanField(
        default=False,
        verbose_name=_("No longer in catalog"),
        help_text=_("True after 'update to current rates' when this product/combination no longer exists."),
    )
    product_supplier = models.ForeignKey(
        "ProductSupplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_lines",
        verbose_name=_("Chosen supplier offer"),
        help_text=_("Catalog supplier row used for this product line when saved."),
    )
    supplier_name_snapshot = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Supplier name (at save)"),
        help_text=_("Frozen supplier label for display if the offer is later removed."),
    )

    class Meta:
        db_table = "catalogus_proposalline"
        ordering = ("proposal", "sort_order", "id")
        verbose_name = _("Proposal line")
        verbose_name_plural = _("Proposal lines")

    def __str__(self):
        return f"{self.name_snapshot or 'Line'} × {self.quantity}"


class ProposalLineOption(models.Model):
    """Selected option (product) for one proposal line. Used when the line is a product with configurable options."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and integrations."),
    )

    proposal_line = models.ForeignKey(
        ProposalLine,
        on_delete=models.CASCADE,
        related_name="selected_options",
        verbose_name=_("Proposal line"),
    )
    option_product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="as_selected_option_in_proposals",
        verbose_name=_("Option (product)"),
    )

    class Meta:
        db_table = "catalogus_proposallineoption"
        ordering = ("proposal_line", "id")
        unique_together = [("proposal_line", "option_product")]
        verbose_name = _("Proposal line option")
        verbose_name_plural = _("Proposal line options")

    def __str__(self):
        return f"{self.proposal_line} – {self.option_product}"


class ProposalContractSnapshot(models.Model):
    """Snapshot of one contract duration at the moment the proposal was saved (name, %, visits, etc.)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and integrations."),
    )

    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="contract_snapshots",
        verbose_name=_("Proposal"),
    )
    contract_duration = models.ForeignKey(
        "ContractDuration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_contract_snapshots",
        verbose_name=_("Contract duration (reference)"),
        help_text=_("Link to current contract duration; null if it was deleted. Used to detect 'removed'."),
    )
    contract_duration_uuid = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=_("Contract duration UUID"),
        help_text=_("UUID of the contract form at save time; used to match even if a new form has the same name."),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    duration_months = models.PositiveIntegerField(verbose_name=_("Duration (months)"))
    hardware_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_("Hardware fee (%)"),
    )
    visits_per_contract = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("6.00"),
        verbose_name=_("Visits per contract period"),
    )

    class Meta:
        db_table = "catalogus_proposalcontractsnapshot"
        ordering = ("proposal", "sort_order", "id")
        verbose_name = _("Proposal contract snapshot")
        verbose_name_plural = _("Proposal contract snapshots")

    def __str__(self):
        return f"{self.proposal} – {self.name}"


class Invoice(models.Model):
    """
    Sales invoice for a saved proposal. Intended flow: proposal → invoice (send to customer) → order.
    Amounts are snapshotted from the proposal line totals at invoice creation.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for URLs and external references."),
    )
    proposal = models.OneToOneField(
        Proposal,
        on_delete=models.CASCADE,
        related_name="invoice",
        verbose_name=_("Proposal"),
    )
    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_SENT, _("Sent")),
        (STATUS_PAID, _("Paid")),
        (STATUS_CANCELLED, _("Cancelled")),
    ]
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name=_("Status"),
        help_text=_("Draft: internal. Sent: issued to the customer (required before creating an order)."),
    )
    invoice_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Invoice number"),
        help_text=_("Optional display number; can be assigned when the invoice is sent."),
    )
    grand_total_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_("Grand total (snapshot)"),
        help_text=_("Total amount from proposal lines at invoice creation."),
    )
    currency_code = models.CharField(
        max_length=3,
        default="EUR",
        verbose_name=_("Currency"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    issued_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Issued at"),
        help_text=_("Set when the invoice is marked as sent."),
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Due date"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
        verbose_name=_("Created by"),
    )

    class Meta:
        db_table = "catalogus_invoice"
        ordering = ("-created_at",)
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")

    def __str__(self) -> str:
        num = self.invoice_number or str(self.uuid)
        return f"{num} ({self.get_status_display()})"


class Order(models.Model):
    """
    Order created from a saved proposal. One order per proposal.
    Tracks high-level status (draft → sent → completed/cancelled) and an optional note.
    Line-level and item-level tracking (ordered at, expected delivery, delivered at) lives on OrderLineItem.
    """

    # Lifecycle: draft (just created), sent (to suppliers), completed (all delivered), cancelled
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and UI anchors."),
    )

    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_SENT, _("Sent")),
        (STATUS_COMPLETED, _("Completed")),
        (STATUS_CANCELLED, _("Cancelled")),
    ]

    proposal = models.OneToOneField(
        Proposal,
        on_delete=models.CASCADE,
        related_name="order",
        verbose_name=_("Proposal"),
    )
    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("Invoice"),
        help_text=_("Invoice issued before this order (proposal → invoice → order)."),
    )
    reference = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Reference"),
        help_text=_("Optional order reference (defaults to proposal reference)."),
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name=_("Status"),
        help_text=_("Draft: not yet sent. Sent: with supplier(s). Completed: all delivered. Cancelled."),
    )
    note = models.TextField(
        blank=True,
        verbose_name=_("Order note"),
        help_text=_("Optional note for this order."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
        verbose_name=_("Created by"),
    )

    class Meta:
        db_table = "catalogus_order"
        ordering = ("-created_at",)
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    def __str__(self):
        return self.reference or str(self.uuid)


class OrderLine(models.Model):
    """
    Links one proposal line to an order. Each line becomes one OrderLine.
    Actual ordering/delivery dates are stored on OrderLineItem (one per product, or one per
    combination item), so OrderLine's date fields are legacy; new code should use OrderLineItem.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and UI anchors."),
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Order"),
    )
    proposal_line = models.OneToOneField(
        ProposalLine,
        on_delete=models.CASCADE,
        related_name="order_line",
        verbose_name=_("Proposal line"),
    )
    ordered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Ordered at"),
        help_text=_("When this line was ordered at the supplier."),
    )
    expected_delivery = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Expected delivery"),
        help_text=_("Expected delivery date."),
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Delivered at"),
        help_text=_("When this line was delivered."),
    )

    class Meta:
        db_table = "catalogus_orderline"
        ordering = ("order", "proposal_line__sort_order", "id")
        verbose_name = _("Order line")
        verbose_name_plural = _("Order lines")

    def __str__(self):
        return f"{self.order} – {self.proposal_line.name_snapshot}"


class OrderLineItem(models.Model):
    """
    One trackable item within an order line; each row has its own ordered_at, expected_delivery, delivered_at.
    - For a simple product line: one OrderLineItem with combination_item=None.
    - For a combination (package): one OrderLineItem per CombinationItem, so each product in the package
      can have its own ordering and delivery dates.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references and integrations."),
    )

    order_line = models.ForeignKey(
        OrderLine,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Order line"),
    )
    # Null for a standalone product line; set when this item is one product inside a combination.
    combination_item = models.ForeignKey(
        "CombinationItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="order_line_items",
        verbose_name=_("Combination item"),
        help_text=_("Set for items inside a combination; empty for a single product line."),
    )
    ordered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Ordered at"),
        help_text=_("When this item was ordered at the supplier."),
    )
    expected_delivery = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Expected delivery"),
        help_text=_("Expected delivery date."),
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Delivered at"),
        help_text=_("When this item was delivered."),
    )

    class Meta:
        db_table = "catalogus_orderlineitem"
        ordering = ("order_line", "combination_item__sort_order", "id")
        verbose_name = _("Order line item")
        verbose_name_plural = _("Order line items")

    def __str__(self):
        if self.combination_item_id:
            return f"{self.order_line} – {self.combination_item}"
        return f"{self.order_line} – item"


class ProposalHistory(models.Model):
    """History entry for a proposal: created, saved, rates updated, line added/removed, etc."""
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for external references."),
    )

    ACTION_CREATED = "created"
    ACTION_SAVED = "saved"
    ACTION_UPDATED_RATES = "updated_rates"
    ACTION_LINE_ADDED = "line_added"
    ACTION_LINE_REMOVED = "line_removed"
    ACTION_QUANTITY_CHANGED = "quantity_changed"
    ACTION_REFERENCE_CHANGED = "reference_changed"
    ACTION_EDITED = "edited"

    ACTION_CHOICES = [
        (ACTION_CREATED, _("Created")),
        (ACTION_SAVED, _("Saved")),
        (ACTION_UPDATED_RATES, _("Prices updated to current")),
        (ACTION_LINE_ADDED, _("Line added")),
        (ACTION_LINE_REMOVED, _("Line removed")),
        (ACTION_QUANTITY_CHANGED, _("Quantity changed")),
        (ACTION_REFERENCE_CHANGED, _("Reference changed")),
        (ACTION_EDITED, _("Edited")),
    ]

    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="history_entries",
        verbose_name=_("Proposal"),
    )
    at = models.DateTimeField(auto_now_add=True, verbose_name=_("At"))
    action = models.CharField(
        max_length=32,
        choices=ACTION_CHOICES,
        verbose_name=_("Action"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional human-readable description."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_history_entries",
        verbose_name=_("User"),
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Details"),
        help_text=_("Optional structured data (e.g. line id, old/new values)."),
    )

    class Meta:
        db_table = "catalogus_proposalhistory"
        ordering = ("-at",)
        verbose_name = _("Proposal history entry")
        verbose_name_plural = _("Proposal history entries")

    def __str__(self):
        return f"{self.proposal} – {self.get_action_display()} ({self.at})"


# --- CRM / Contacts (Organizations, Persons, pivot) ---------------------------------


class Organization(models.Model):
    """
    Single table for companies that can hold multiple roles (supplier, client, lead, network).
    Roles are stored in OrganizationRole (query-friendly); a company can be supplier + client at once.
    """

    PROMOTION_AUTO = "auto"
    PROMOTION_MANUAL_CLIENT = "manual_client"
    PROMOTION_MANUAL_LEAD = "manual_lead"
    PROMOTION_OVERRIDE_CHOICES = [
        (PROMOTION_AUTO, _("Automatic (first invoice/shipment promotes lead to client)")),
        (PROMOTION_MANUAL_CLIENT, _("Manual: always treat as client (adds CLIENT role)")),
        (PROMOTION_MANUAL_LEAD, _("Manual: keep as lead (no auto promotion from invoice/shipment)")),
    ]

    PIPELINE_NEW = "new"
    PIPELINE_CONTACTED = "contacted"
    PIPELINE_QUALIFIED = "qualified"
    PIPELINE_PROPOSAL = "proposal"
    PIPELINE_NEGOTIATION = "negotiation"
    PIPELINE_WON = "won"
    PIPELINE_LOST = "lost"
    LEAD_PIPELINE_CHOICES = [
        (PIPELINE_NEW, _("New")),
        (PIPELINE_CONTACTED, _("Contacted")),
        (PIPELINE_QUALIFIED, _("Qualified")),
        (PIPELINE_PROPOSAL, _("Proposal")),
        (PIPELINE_NEGOTIATION, _("Negotiation")),
        (PIPELINE_WON, _("Won")),
        (PIPELINE_LOST, _("Lost")),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
        help_text=_("Stable identifier for URLs and integrations."),
    )
    name = models.CharField(max_length=255, verbose_name=_("Company name"))
    legal_name = models.CharField(max_length=255, blank=True, verbose_name=_("Legal name"))
    vat_number = models.CharField(max_length=64, blank=True, verbose_name=_("VAT number"))
    coc_number = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Chamber of Commerce number"),
        help_text=_("KvK / trade register number."),
    )

    billing_line1 = models.CharField(max_length=255, blank=True, verbose_name=_("Billing address line 1"))
    billing_line2 = models.CharField(max_length=255, blank=True, verbose_name=_("Billing address line 2"))
    billing_city = models.CharField(max_length=128, blank=True, verbose_name=_("Billing city"))
    billing_postal_code = models.CharField(max_length=32, blank=True, verbose_name=_("Billing postal code"))
    billing_country = models.CharField(max_length=128, blank=True, verbose_name=_("Billing country"))

    shipping_line1 = models.CharField(max_length=255, blank=True, verbose_name=_("Shipping address line 1"))
    shipping_line2 = models.CharField(max_length=255, blank=True, verbose_name=_("Shipping address line 2"))
    shipping_city = models.CharField(max_length=128, blank=True, verbose_name=_("Shipping city"))
    shipping_postal_code = models.CharField(max_length=32, blank=True, verbose_name=_("Shipping postal code"))
    shipping_country = models.CharField(max_length=128, blank=True, verbose_name=_("Shipping country"))

    email = models.EmailField(blank=True, verbose_name=_("General email"))
    phone = models.CharField(max_length=64, blank=True, verbose_name=_("General phone"))
    website = models.URLField(blank=True, verbose_name=_("Website"))

    iban = models.CharField(max_length=64, blank=True, verbose_name=_("IBAN"))
    bic_swift = models.CharField(max_length=32, blank=True, verbose_name=_("BIC / SWIFT"))
    payment_terms = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Payment terms"),
        help_text=_("e.g. Net 30"),
    )
    currency = models.CharField(max_length=3, default="EUR", verbose_name=_("Currency"))
    credit_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Credit limit"),
    )

    incoterms = models.CharField(max_length=32, blank=True, verbose_name=_("Incoterms"))
    lead_time_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Lead time (days)"),
    )
    moq = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("MOQ"),
        help_text=_("Minimum order quantity (text or number)."),
    )

    network_value_proposition = models.TextField(
        blank=True,
        verbose_name=_("Value proposition"),
        help_text=_("Why this network partner is useful (when NETWORK role applies)."),
    )
    network_industry_niche = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Industry / niche"),
        help_text=_("For network partners."),
    )

    lead_pipeline_status = models.CharField(
        max_length=32,
        choices=LEAD_PIPELINE_CHOICES,
        blank=True,
        verbose_name=_("Lead pipeline status"),
        help_text=_("Used for leads in the pipeline; optional for other roles."),
    )
    client_since = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Client since"),
        help_text=_("Set when the organization first became a client (auto or manual)."),
    )
    suppress_auto_client_promotion = models.BooleanField(
        default=False,
        verbose_name=_("Suppress automatic client promotion"),
        help_text=_("If enabled, registering invoices/shipments will not promote LEAD → CLIENT."),
    )
    client_promotion_override = models.CharField(
        max_length=32,
        choices=PROMOTION_OVERRIDE_CHOICES,
        default=PROMOTION_AUTO,
        verbose_name=_("Client promotion mode"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        db_table = "catalogus_organization"
        ordering = ("name",)
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")
        constraints = [
            models.UniqueConstraint(
                fields=["vat_number"],
                name="uniq_catalogus_organization_vat_nonempty",
                condition=~models.Q(vat_number=""),
            ),
            models.UniqueConstraint(
                fields=["coc_number"],
                name="uniq_catalogus_organization_coc_nonempty",
                condition=~models.Q(coc_number=""),
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()
        from pricelist.services.organization_identity import (
            coc_is_duplicate,
            normalize_coc,
            normalize_vat,
            vat_is_duplicate,
        )

        self.vat_number = normalize_vat(self.vat_number)
        self.coc_number = normalize_coc(self.coc_number)
        errors = {}
        if self.vat_number and vat_is_duplicate(self.vat_number, exclude_pk=self.pk):
            errors["vat_number"] = ValidationError(
                _("This VAT number is already registered."),
                code="duplicate_vat",
            )
        if self.coc_number and coc_is_duplicate(self.coc_number, exclude_pk=self.pk):
            errors["coc_number"] = ValidationError(
                _("This Chamber of Commerce number is already registered."),
                code="duplicate_coc",
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        from pricelist.services.organization_identity import normalize_coc, normalize_vat

        self.vat_number = normalize_vat(self.vat_number)
        self.coc_number = normalize_coc(self.coc_number)
        super().save(*args, **kwargs)
        if self.client_promotion_override == self.PROMOTION_MANUAL_CLIENT:
            OrganizationRole.objects.get_or_create(
                organization=self,
                role=OrganizationRole.ROLE_CLIENT,
            )
        if not self.role_assignments.exists():
            OrganizationRole.objects.get_or_create(
                organization=self,
                role=OrganizationRole.ROLE_LEAD,
            )


class OrganizationRole(models.Model):
    """One role flag per organization (supports multiple simultaneous roles)."""

    ROLE_SUPPLIER = "SUPPLIER"
    ROLE_CLIENT = "CLIENT"
    ROLE_LEAD = "LEAD"
    ROLE_NETWORK = "NETWORK"
    ROLE_CHOICES = [
        (ROLE_SUPPLIER, _("Supplier")),
        (ROLE_CLIENT, _("Client")),
        (ROLE_LEAD, _("Lead")),
        (ROLE_NETWORK, _("Network")),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="role_assignments",
        verbose_name=_("Organization"),
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, verbose_name=_("Role"))

    class Meta:
        db_table = "catalogus_organizationrole"
        verbose_name = _("Organization role")
        verbose_name_plural = _("Organization roles")
        constraints = [
            models.UniqueConstraint(fields=["organization", "role"], name="uniq_organization_role"),
        ]

    def __str__(self) -> str:
        return f"{self.organization} – {self.get_role_display()}"


class Department(models.Model):
    """Department within an organization (e.g. Accounts Payable, Customer Support)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="departments",
        verbose_name=_("Organization"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Department name"))
    email = models.EmailField(blank=True, verbose_name=_("General email"))
    phone = models.CharField(max_length=64, blank=True, verbose_name=_("General phone"))
    notes = models.TextField(blank=True, verbose_name=_("Internal notes"))

    class Meta:
        db_table = "catalogus_department"
        ordering = ("organization", "name")
        verbose_name = _("Department")
        verbose_name_plural = _("Departments")

    def __str__(self) -> str:
        return f"{self.organization} – {self.name}"


def _empty_json_list():
    return []


class Person(models.Model):
    """Central directory of people; link to organizations via OrganizationPerson."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    first_name = models.CharField(max_length=128, verbose_name=_("First name"))
    last_name = models.CharField(max_length=128, verbose_name=_("Last name"))
    personal_email = models.EmailField(blank=True, verbose_name=_("Personal email"))
    personal_mobile = models.CharField(max_length=64, blank=True, verbose_name=_("Personal mobile"))
    linkedin_url = models.URLField(blank=True, verbose_name=_("LinkedIn URL"))

    date_of_birth = models.DateField(null=True, blank=True, verbose_name=_("Date of birth"))
    communication_preferences = models.TextField(
        blank=True,
        verbose_name=_("Communication preferences"),
        help_text=_("How and when they prefer to be contacted."),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        db_table = "catalogus_person"
        ordering = ("last_name", "first_name")
        verbose_name = _("Person")
        verbose_name_plural = _("Persons")

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or _("(Unnamed person)")


class PersonHobby(models.Model):
    """Single hobby or interest line for a person (editable independently)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="hobbies",
        verbose_name=_("Person"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Hobby or interest"))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_("Sort order"))

    class Meta:
        db_table = "catalogus_personhobby"
        ordering = ("sort_order", "name", "id")
        verbose_name = _("Hobby or interest")
        verbose_name_plural = _("Hobbies & interests")

    def __str__(self) -> str:
        return self.name


class PersonEvent(models.Model):
    """
    Dated personal event (birthday, anniversary, follow-up) with optional reminder offset.
    Distinct from PersonLifeEvent (relationship log notes).
    """

    REMINDER_NONE = "none"
    REMINDER_ON_DAY = "on_day"
    REMINDER_1_DAY = "1_day_before"
    REMINDER_1_WEEK = "1_week_before"
    REMINDER_2_WEEKS = "2_weeks_before"
    REMINDER_1_MONTH = "1_month_before"
    REMINDER_CHOICES = [
        (REMINDER_NONE, _("No reminder")),
        (REMINDER_ON_DAY, _("On the day")),
        (REMINDER_1_DAY, _("One day before")),
        (REMINDER_1_WEEK, _("One week before")),
        (REMINDER_2_WEEKS, _("Two weeks before")),
        (REMINDER_1_MONTH, _("One month before")),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="personal_events",
        verbose_name=_("Person"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Event name"))
    event_date = models.DateField(verbose_name=_("Date"))
    reminder = models.CharField(
        max_length=32,
        choices=REMINDER_CHOICES,
        default=REMINDER_NONE,
        verbose_name=_("Reminder"),
        help_text=_("When you want to be reminded relative to the event date."),
    )

    class Meta:
        db_table = "catalogus_personevent"
        ordering = ("event_date", "name", "id")
        verbose_name = _("Event")
        verbose_name_plural = _("Events")

    def __str__(self) -> str:
        return f"{self.name} ({self.event_date})"


class PersonLifeEvent(models.Model):
    """Timestamped personal note (Joe Girard-style relationship log)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="life_events",
        verbose_name=_("Person"),
    )
    occurred_on = models.DateField(verbose_name=_("Date"))
    note = models.TextField(verbose_name=_("Note"))

    class Meta:
        db_table = "catalogus_personlifeevent"
        ordering = ("-occurred_on", "-id")
        verbose_name = _("Person life event")
        verbose_name_plural = _("Person life events")

    def __str__(self) -> str:
        return f"{self.person} – {self.occurred_on}"


class OrganizationPerson(models.Model):
    """Pivot: person ↔ organization (and optional department), with job-specific contact fields."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Organization"),
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Person"),
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name=_("Department"),
    )
    job_title = models.CharField(max_length=255, blank=True, verbose_name=_("Job title"))
    company_email = models.EmailField(blank=True, verbose_name=_("Company email"))
    company_phone = models.CharField(max_length=64, blank=True, verbose_name=_("Company phone"))
    phone_extension = models.CharField(max_length=32, blank=True, verbose_name=_("Extension"))
    is_primary_contact = models.BooleanField(default=False, verbose_name=_("Primary contact"))

    class Meta:
        db_table = "catalogus_organizationperson"
        ordering = ("organization", "person")
        verbose_name = _("Organization membership")
        verbose_name_plural = _("Organization memberships")

    def __str__(self) -> str:
        return f"{self.person} @ {self.organization}"


class OrganizationNetworkLink(models.Model):
    """
    Links a network-partner organization to another organization (supplier, client, or lead).
    The same network partner can be linked to many suppliers and many clients.
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    network_organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="network_partner_links",
        verbose_name=_("Network partner"),
        help_text=_("Organization with the network/partner role."),
    )
    linked_organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="counterparty_network_links",
        verbose_name=_("Linked company"),
        help_text=_("Supplier, client, or lead organization this relationship is recorded on."),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        db_table = "catalogus_organizationnetworklink"
        ordering = ("network_organization", "linked_organization")
        verbose_name = _("Network link")
        verbose_name_plural = _("Network links")
        constraints = [
            models.UniqueConstraint(
                fields=("network_organization", "linked_organization"),
                name="uniq_organization_network_link_pair",
            ),
        ]

    def clean(self):
        super().clean()
        if self.network_organization_id and self.linked_organization_id:
            if self.network_organization_id == self.linked_organization_id:
                raise ValidationError(
                    _("Network partner and linked company must be different organizations.")
                )

    def __str__(self) -> str:
        return f"{self.network_organization} ↔ {self.linked_organization}"


class OrganizationInvoice(models.Model):
    """Minimal invoice record to drive LEAD → CLIENT promotion (first registered invoice)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name=_("Organization"),
    )
    invoice_number = models.CharField(max_length=128, verbose_name=_("Invoice number"))
    issued_on = models.DateField(verbose_name=_("Issue date"))
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Amount"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        db_table = "catalogus_organizationinvoice"
        ordering = ("-issued_on", "-id")
        verbose_name = _("Organization invoice")
        verbose_name_plural = _("Organization invoices")

    def __str__(self) -> str:
        return f"{self.organization} – {self.invoice_number}"


class OrganizationShipment(models.Model):
    """Minimal shipment record to drive LEAD → CLIENT promotion (first registered shipment)."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name=_("UUID"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name=_("Organization"),
    )
    reference = models.CharField(max_length=128, verbose_name=_("Shipment reference"))
    shipped_on = models.DateField(verbose_name=_("Ship date"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        db_table = "catalogus_organizationshipment"
        ordering = ("-shipped_on", "-id")
        verbose_name = _("Organization shipment")
        verbose_name_plural = _("Organization shipments")

    def __str__(self) -> str:
        return f"{self.organization} – {self.reference}"


@receiver(post_save, sender=OrganizationInvoice)
def _organization_invoice_promote_client(sender, instance, created, **kwargs):
    if not created:
        return
    from pricelist.services.contacts_promotion import maybe_promote_lead_to_client

    maybe_promote_lead_to_client(instance.organization)


@receiver(post_save, sender=OrganizationShipment)
def _organization_shipment_promote_client(sender, instance, created, **kwargs):
    if not created:
        return
    from pricelist.services.contacts_promotion import maybe_promote_lead_to_client

    maybe_promote_lead_to_client(instance.organization)


@receiver(pre_save, sender=Product)
def product_price_pre_save(sender, instance: Product, **kwargs):
    """Track when a product's cost price changes and create a PriceHistory record."""
    from datetime import date

    if not instance.pk:
        if instance.cost_price is not None and instance.price_last_changed is None:
            instance.price_last_changed = date.today()
        return

    try:
        old_instance = Product.objects.get(pk=instance.pk)
    except Product.DoesNotExist:
        return

    if old_instance.cost_price != instance.cost_price:
        today = date.today()
        instance.price_last_changed = today
        if old_instance.cost_price is not None and instance.cost_price is not None:
            PriceHistory.objects.create(
                product=instance,
                previous_cost_price=old_instance.cost_price,
                new_cost_price=instance.cost_price,
                change_date=today,
                sales_price_at_date=instance.calculated_sales_price,
            )
