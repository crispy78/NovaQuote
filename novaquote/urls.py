"""
URL configuration for NovaQuote project.
"""
from django.contrib import admin
from django.views.generic import RedirectView
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from pricelist import error_views

handler403 = error_views.permission_denied

urlpatterns = [
    # Backward-compatible redirect for old bookmark under /admin.
    path(
        "admin/proposal/saved/",
        RedirectView.as_view(pattern_name="pricelist:proposal_list", permanent=False),
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("pricelist.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
