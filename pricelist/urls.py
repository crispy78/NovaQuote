from django.urls import path

from . import catalog_views, contacts_views, invoice_views
from .views import (
    home_view,
    order_create_view,
    order_detail_view,
    order_list_view,
    price_list_combinations_view,
    price_list_pdf_view,
    price_list_products_view,
    price_list_view,
    product_detail_view,
    proposal_detail_view,
    proposal_history_view,
    proposal_list_view,
    proposal_save_view,
    proposal_update_rates_view,
    proposal_view,
)

app_name = "pricelist"

urlpatterns = [
    path("", home_view, name="home"),
    path("price-list/", price_list_view, name="price_list"),
    path("price-list/products/", price_list_products_view, name="price_list_products"),
    path("price-list/combinations/", price_list_combinations_view, name="price_list_combinations"),
    path("price-list/pdf/", price_list_pdf_view, name="price_list_pdf"),
    # Catalog management (frontend)
    path("catalog/products/", catalog_views.catalog_product_list_view, name="catalog_product_list"),
    path("catalog/products/add/", catalog_views.catalog_product_create_view, name="catalog_product_create"),
    path(
        "catalog/products/<uuid:article_uuid>/edit/",
        catalog_views.catalog_product_edit_view,
        name="catalog_product_edit",
    ),
    path(
        "catalog/products/<uuid:article_uuid>/remove/",
        catalog_views.catalog_product_remove_view,
        name="catalog_product_remove",
    ),
    path("catalog/products/trash/", catalog_views.catalog_product_trash_view, name="catalog_product_trash"),
    path(
        "catalog/products/trash/<uuid:article_uuid>/restore/",
        catalog_views.catalog_product_restore_view,
        name="catalog_product_restore",
    ),
    path(
        "catalog/products/trash/<uuid:article_uuid>/purge/",
        catalog_views.catalog_product_purge_view,
        name="catalog_product_purge",
    ),
    path("catalog/combinations/", catalog_views.catalog_combination_list_view, name="catalog_combination_list"),
    path(
        "catalog/combinations/add/",
        catalog_views.catalog_combination_create_view,
        name="catalog_combination_create",
    ),
    path(
        "catalog/combinations/<uuid:combo_uuid>/edit/",
        catalog_views.catalog_combination_edit_view,
        name="catalog_combination_edit",
    ),
    path(
        "catalog/combinations/<uuid:combo_uuid>/remove/",
        catalog_views.catalog_combination_remove_view,
        name="catalog_combination_remove",
    ),
    path(
        "catalog/combinations/trash/",
        catalog_views.catalog_combination_trash_view,
        name="catalog_combination_trash",
    ),
    path(
        "catalog/combinations/trash/<uuid:combo_uuid>/restore/",
        catalog_views.catalog_combination_restore_view,
        name="catalog_combination_restore",
    ),
    path(
        "catalog/combinations/trash/<uuid:combo_uuid>/purge/",
        catalog_views.catalog_combination_purge_view,
        name="catalog_combination_purge",
    ),
    path("catalog/images/", catalog_views.catalog_image_list_view, name="catalog_image_list"),
    path("catalog/categories/", catalog_views.catalog_category_list_view, name="catalog_category_list"),
    path("catalog/categories/add/", catalog_views.catalog_category_create_view, name="catalog_category_create"),
    path(
        "catalog/categories/<uuid:category_uuid>/edit/",
        catalog_views.catalog_category_edit_view,
        name="catalog_category_edit",
    ),
    path(
        "catalog/categories/<uuid:category_uuid>/remove/",
        catalog_views.catalog_category_delete_view,
        name="catalog_category_delete",
    ),
    path("catalog/profit-profiles/", catalog_views.catalog_profit_profile_list_view, name="catalog_profit_profile_list"),
    path(
        "catalog/profit-profiles/add/",
        catalog_views.catalog_profit_profile_create_view,
        name="catalog_profit_profile_create",
    ),
    path(
        "catalog/profit-profiles/<uuid:profile_uuid>/edit/",
        catalog_views.catalog_profit_profile_edit_view,
        name="catalog_profit_profile_edit",
    ),
    path(
        "catalog/profit-profiles/<uuid:profile_uuid>/remove/",
        catalog_views.catalog_profit_profile_delete_view,
        name="catalog_profit_profile_delete",
    ),
    path("product/<uuid:uuid>/", product_detail_view, name="product_detail"),
    path("proposal/", proposal_view, name="proposal"),
    path("proposal/save/", proposal_save_view, name="proposal_save"),
    path("proposal/saved/", proposal_list_view, name="proposal_list"),
    path("proposal/saved/<str:identifier>/", proposal_detail_view, name="proposal_detail"),
    path("proposal/saved/<str:identifier>/update-rates/", proposal_update_rates_view, name="proposal_update_rates"),
    path("proposal/saved/<str:identifier>/history/", proposal_history_view, name="proposal_history"),
    # Invoicing (proposal → invoice → order)
    path("invoices/", invoice_views.invoice_list_view, name="invoice_list"),
    path("invoices/create/<str:identifier>/", invoice_views.invoice_create_view, name="invoice_create"),
    path("invoices/<uuid:pk>/", invoice_views.invoice_detail_view, name="invoice_detail"),
    path("invoices/<uuid:pk>/status/", invoice_views.invoice_update_status_view, name="invoice_update_status"),
    path(
        "invoices/<uuid:pk>/payments/add/",
        invoice_views.invoice_record_payment_view,
        name="invoice_payment_add",
    ),
    path(
        "invoices/<uuid:pk>/payments/<uuid:payment_uuid>/delete/",
        invoice_views.invoice_delete_payment_view,
        name="invoice_payment_delete",
    ),
    path("orders/", order_list_view, name="order_list"),
    path("orders/create/<str:identifier>/", order_create_view, name="order_create"),
    # UUID-based detail view (external integrations / stable links)
    path("orders/<uuid:pk>/", order_detail_view, name="order_detail_uuid"),
    # Legacy int PK-based route
    path("orders/<int:pk>/", order_detail_view, name="order_detail"),
    # Contacts (CRM)
    path("contacts/suppliers/", contacts_views.contacts_suppliers_view, name="contacts_suppliers"),
    path("contacts/clients/", contacts_views.contacts_clients_view, name="contacts_clients"),
    path("contacts/leads/", contacts_views.contacts_leads_view, name="contacts_leads"),
    path("contacts/network/", contacts_views.contacts_network_view, name="contacts_network"),
    path("contacts/persons/", contacts_views.contacts_persons_view, name="contacts_persons"),
    path(
        "contacts/organizations/<uuid:org_uuid>/",
        contacts_views.contacts_organization_detail_view,
        name="contacts_organization_detail",
    ),
    path(
        "contacts/persons/<uuid:person_uuid>/",
        contacts_views.contacts_person_detail_view,
        name="contacts_person_detail",
    ),
    path(
        "contacts/api/organization-identity/",
        contacts_views.contacts_organization_identity_check_view,
        name="contacts_organization_identity_check",
    ),
    path("contacts/organizations/add/", contacts_views.contacts_organization_create_view, name="contacts_organization_create"),
    path(
        "contacts/organizations/<uuid:org_uuid>/edit/",
        contacts_views.contacts_organization_edit_view,
        name="contacts_organization_edit",
    ),
    path(
        "contacts/organizations/<uuid:org_uuid>/departments/add/",
        contacts_views.contacts_department_create_view,
        name="contacts_department_create",
    ),
    path(
        "contacts/organizations/<uuid:org_uuid>/departments/<uuid:dept_uuid>/edit/",
        contacts_views.contacts_department_edit_view,
        name="contacts_department_edit",
    ),
    path(
        "contacts/organizations/<uuid:org_uuid>/memberships/add/",
        contacts_views.contacts_membership_create_view,
        name="contacts_membership_create",
    ),
    path(
        "contacts/organizations/<uuid:org_uuid>/network-links/add/",
        contacts_views.contacts_network_link_add_view,
        name="contacts_network_link_add",
    ),
    path(
        "contacts/organizations/<uuid:org_uuid>/network-links/<uuid:link_uuid>/delete/",
        contacts_views.contacts_network_link_delete_view,
        name="contacts_network_link_delete",
    ),
    path("contacts/persons/add/", contacts_views.contacts_person_create_view, name="contacts_person_create"),
    path(
        "contacts/persons/<uuid:person_uuid>/memberships/add/",
        contacts_views.contacts_person_membership_add_view,
        name="contacts_person_membership_add",
    ),
    path(
        "contacts/persons/<uuid:person_uuid>/edit/",
        contacts_views.contacts_person_edit_view,
        name="contacts_person_edit",
    ),
    path(
        "contacts/persons/<uuid:person_uuid>/life-events/add/",
        contacts_views.contacts_life_event_create_view,
        name="contacts_life_event_create",
    ),
]

