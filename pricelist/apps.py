from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogusConfig(AppConfig):
    name = "pricelist"
    verbose_name = _("Catalog")
