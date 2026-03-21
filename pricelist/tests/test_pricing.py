"""Core catalog pricing and multi-supplier helpers."""

from decimal import Decimal

from django.test import TestCase

from pricelist.models import Product, ProductSupplier, ProfitProfile, Supplier, round_price
from pricelist.services.product_supplier_offers import pick_product_supplier, resolve_supplier_for_proposal_line


class ProfitProfileMarkupTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(name="Supplier A")
        self.profile = ProfitProfile.objects.create(
            name="Std",
            markup_percentage=Decimal("10.00"),
            markup_fixed=Decimal("5.00"),
        )
        self.product = Product.objects.create(
            brand="Brand",
            model_type="Model",
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            profit_profile=self.profile,
        )
        ProductSupplier.objects.create(
            product=self.product,
            supplier=self.supplier,
            cost_price=Decimal("100.00"),
            is_preferred=True,
        )

    def test_calculated_sales_price(self):
        # 100 * 1.10 + 5 = 115
        self.assertEqual(self.product.calculated_sales_price, Decimal("115.00"))

    def test_round_price_syntax(self):
        self.assertEqual(round_price(Decimal("10.04"), "0.05"), Decimal("10.05"))
        self.assertEqual(round_price(Decimal("10.04"), "1-0.01"), Decimal("9.99"))


class ProductSupplierPreferredSyncTests(TestCase):
    def test_save_updates_product_mirror_fields(self):
        s = Supplier.objects.create(name="S")
        p = ProfitProfile.objects.create(name="P", markup_percentage=Decimal("0"), markup_fixed=Decimal("0"))
        prod = Product.objects.create(
            brand="B",
            model_type="M",
            supplier=s,
            cost_price=Decimal("10.00"),
            profit_profile=p,
        )
        ProductSupplier.objects.create(
            product=prod,
            supplier=s,
            cost_price=Decimal("77.50"),
            supplier_order_number="ORD-1",
            is_preferred=True,
        )
        prod.refresh_from_db()
        self.assertEqual(prod.cost_price, Decimal("77.50"))
        self.assertEqual(prod.supplier_order_number, "ORD-1")


class ProductSupplierStrategyTests(TestCase):
    def setUp(self):
        self.s_cheap = Supplier.objects.create(name="CheapCo")
        self.s_fast = Supplier.objects.create(name="FastCo")
        self.profile = ProfitProfile.objects.create(name="P", markup_percentage=Decimal("0"), markup_fixed=Decimal("0"))
        self.product = Product.objects.create(
            brand="X",
            model_type="Y",
            supplier=self.s_cheap,
            cost_price=Decimal("100"),
            profit_profile=self.profile,
        )
        ProductSupplier.objects.create(
            product=self.product,
            supplier=self.s_cheap,
            cost_price=Decimal("100"),
            lead_time_days=20,
            payment_terms_days=30,
            is_preferred=True,
            sort_order=0,
        )
        ProductSupplier.objects.create(
            product=self.product,
            supplier=self.s_fast,
            cost_price=Decimal("120"),
            lead_time_days=5,
            payment_terms_days=60,
            is_preferred=False,
            sort_order=1,
        )

    def test_pick_cheapest(self):
        ps = pick_product_supplier(self.product, "cheapest")
        self.assertEqual(ps.supplier_id, self.s_cheap.pk)

    def test_pick_fastest(self):
        ps = pick_product_supplier(self.product, "fastest")
        self.assertEqual(ps.supplier_id, self.s_fast.pk)

    def test_resolve_with_invalid_posted_uuid_falls_back_to_preferred(self):
        ps = resolve_supplier_for_proposal_line(self.product, "00000000-0000-4000-8000-000000000099")
        self.assertTrue(ps.is_preferred)
