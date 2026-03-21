# Rename all Dutch model fields to English for international use.
# Also update Combination offer_type choice values to English.

from django.db import migrations


def update_offer_type_values_forward(apps, schema_editor):
    # Use historical model name: state at this point still has "Combinatie"
    Combinatie = apps.get_model("pricelist", "Combinatie")
    mapping = {
        "geen": "none",
        "vast_bedrag": "fixed_amount",
        "korting_bedrag": "discount_amount",
        "korting_percentage": "discount_percentage",
    }
    for old, new in mapping.items():
        Combinatie.objects.filter(aanbieding_type=old).update(aanbieding_type=new)


def update_offer_type_values_reverse(apps, schema_editor):
    Combinatie = apps.get_model("pricelist", "Combinatie")
    mapping = {
        "none": "geen",
        "fixed_amount": "vast_bedrag",
        "discount_amount": "korting_bedrag",
        "discount_percentage": "korting_percentage",
    }
    for old, new in mapping.items():
        Combinatie.objects.filter(aanbieding_type=old).update(aanbieding_type=new)


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0034_rename_combinatieitem_id_m2m"),
    ]

    operations = [
        migrations.RunPython(update_offer_type_values_forward, update_offer_type_values_reverse),
        # Rename models so state matches current models.py (Combinatie/CombinatieItem done in 0036 via state only)
        migrations.RenameModel(old_name="Leverancier", new_name="Supplier"),
        migrations.RenameModel(old_name="Categorie", new_name="Category"),
        migrations.RenameModel(old_name="AlgemeneInstellingen", new_name="GeneralSettings"),
        migrations.RenameModel(old_name="WinstProfiel", new_name="ProfitProfile"),
        migrations.RenameModel(old_name="PrijsHistorie", new_name="PriceHistory"),
        migrations.RenameModel(old_name="ProductOptie", new_name="ProductOption"),
        # Supplier
        migrations.RenameField(model_name="supplier", old_name="naam", new_name="name"),
        migrations.RenameField(model_name="supplier", old_name="contactpersoon", new_name="contact_person"),
        # Category
        migrations.RenameField(model_name="category", old_name="naam", new_name="name"),
        migrations.RenameField(model_name="category", old_name="volgorde", new_name="sort_order"),
        # GeneralSettings
        migrations.RenameField(model_name="generalsettings", old_name="valuta", new_name="currency"),
        migrations.RenameField(model_name="generalsettings", old_name="afronding", new_name="rounding"),
        migrations.RenameField(model_name="generalsettings", old_name="getalnotatie", new_name="number_format"),
        migrations.RenameField(model_name="generalsettings", old_name="minimale_marge_percentage", new_name="minimum_margin_percentage"),
        migrations.RenameField(model_name="generalsettings", old_name="toon_prijsverloop_grafiek_productpagina", new_name="show_price_history_chart_on_product_page"),
        migrations.RenameField(model_name="generalsettings", old_name="toon_prijsverloop_inkoop_productpagina", new_name="show_cost_in_price_history_chart"),
        migrations.RenameField(model_name="generalsettings", old_name="toon_prijsverloop_verkoop_productpagina", new_name="show_sales_in_price_history_chart"),
        migrations.RenameField(model_name="generalsettings", old_name="toon_leverancier_frontend", new_name="show_supplier_on_frontend"),
        migrations.RenameField(model_name="generalsettings", old_name="toon_categorie_frontend", new_name="show_category_on_frontend"),
        migrations.RenameField(model_name="generalsettings", old_name="taal", new_name="language"),
        # ProfitProfile
        migrations.RenameField(model_name="profitprofile", old_name="naam", new_name="name"),
        migrations.RenameField(model_name="profitprofile", old_name="opslag_percentage", new_name="markup_percentage"),
        migrations.RenameField(model_name="profitprofile", old_name="opslag_fixed", new_name="markup_fixed"),
        migrations.RenameField(model_name="profitprofile", old_name="actief", new_name="is_active"),
        # Product
        migrations.RenameField(model_name="product", old_name="merk", new_name="brand"),
        migrations.RenameField(model_name="product", old_name="type", new_name="model_type"),
        migrations.RenameField(model_name="product", old_name="naam", new_name="name"),
        migrations.RenameField(model_name="product", old_name="artikelnummer", new_name="article_number"),
        migrations.RenameField(model_name="product", old_name="omschrijving", new_name="description"),
        migrations.RenameField(model_name="product", old_name="leverancier", new_name="supplier"),
        migrations.RenameField(model_name="product", old_name="categorie", new_name="category"),
        migrations.RenameField(model_name="product", old_name="afbeelding", new_name="image"),
        migrations.RenameField(model_name="product", old_name="bestelnummer_leverancier", new_name="supplier_order_number"),
        migrations.RenameField(model_name="product", old_name="inkoopprijs", new_name="cost_price"),
        migrations.RenameField(model_name="product", old_name="vaste_verkoopprijs", new_name="fixed_sales_price"),
        migrations.RenameField(model_name="product", old_name="winstprofiel", new_name="profit_profile"),
        migrations.RenameField(model_name="product", old_name="prijs_laatst_gewijzigd", new_name="price_last_changed"),
        migrations.RenameField(model_name="product", old_name="prijs_laatst_gecontroleerd", new_name="price_last_checked"),
        migrations.RenameField(model_name="product", old_name="toon_in_prijslijst", new_name="show_in_price_list"),
        migrations.RenameField(model_name="product", old_name="marge_product", new_name="is_margin_product"),
        migrations.RenameField(model_name="product", old_name="aangemaakt_op", new_name="created_at"),
        # ProductOption
        migrations.RenameField(model_name="productoption", old_name="hoofdproduct", new_name="main_product"),
        migrations.RenameField(model_name="productoption", old_name="optie_product", new_name="option_product"),
        migrations.RenameField(model_name="productoption", old_name="korte_omschrijving", new_name="short_description"),
        migrations.RenameField(model_name="productoption", old_name="volgorde", new_name="sort_order"),
        # PriceHistory
        migrations.RenameField(model_name="pricehistory", old_name="oude_inkoopprijs", new_name="previous_cost_price"),
        migrations.RenameField(model_name="pricehistory", old_name="nieuwe_inkoopprijs", new_name="new_cost_price"),
        migrations.RenameField(model_name="pricehistory", old_name="wijzigingsdatum", new_name="change_date"),
        migrations.RenameField(model_name="pricehistory", old_name="verkoopprijs_op_datum", new_name="sales_price_at_date"),
        # CombinationItem: M2M table already has combinationitem_id (0034); just rename table
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name="combinatieitem", old_name="geselecteerde_opties", new_name="selected_options"),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE catalogus_combinatieitem_geselecteerde_opties RENAME TO catalogus_combinationitem_selected_options",
                    "ALTER TABLE catalogus_combinationitem_selected_options RENAME TO catalogus_combinatieitem_geselecteerde_opties",
                ),
            ],
        ),
        migrations.RenameField(model_name="combinatieitem", old_name="combinatie", new_name="combination"),
        migrations.RenameField(model_name="combinatieitem", old_name="volgorde", new_name="sort_order"),
        # Combination (state still has Combinatie; use combinatie)
        migrations.RenameField(model_name="combinatie", old_name="naam", new_name="name"),
        migrations.RenameField(model_name="combinatie", old_name="omschrijving", new_name="description"),
        # M2M producten->products: table has combination_id (0033); just rename table
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name="combinatie", old_name="producten", new_name="products"),
            ],
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE catalogus_combinatie_producten RENAME TO catalogus_combination_products",
                    "ALTER TABLE catalogus_combination_products RENAME TO catalogus_combinatie_producten",
                ),
            ],
        ),
        migrations.RenameField(model_name="combinatie", old_name="combinatie_verkoopprijs", new_name="combination_sales_price"),
        migrations.RenameField(model_name="combinatie", old_name="aanbieding_type", new_name="offer_type"),
        migrations.RenameField(model_name="combinatie", old_name="aanbieding_vast_bedrag", new_name="offer_fixed_amount"),
        migrations.RenameField(model_name="combinatie", old_name="aanbieding_korting_bedrag", new_name="discount_amount"),
        migrations.RenameField(model_name="combinatie", old_name="aanbieding_korting_percentage", new_name="discount_percentage"),
    ]
