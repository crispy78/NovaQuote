"""Frontend role capabilities on URLs."""

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from pricelist.models import FrontendRole, UserFrontendProfile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class FrontendRoleAccessTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_sales_role_gets_price_list_but_not_catalog(self):
        role = FrontendRole.objects.get(slug=FrontendRole.SLUG_SALES)
        u = User.objects.create_user("sam", "sam@example.com", "secret")
        UserFrontendProfile.objects.create(user=u, role=role)
        self.client.login(username="sam", password="secret")
        self.assertEqual(self.client.get("/price-list/products/").status_code, 200)
        r = self.client.get("/catalog/products/")
        self.assertEqual(r.status_code, 403)
        self.assertIn(b"Back to home", r.content)

    def test_procurement_gets_orders_not_proposals(self):
        role = FrontendRole.objects.get(slug=FrontendRole.SLUG_PROCUREMENT)
        u = User.objects.create_user("pat", "pat@example.com", "secret")
        UserFrontendProfile.objects.create(user=u, role=role)
        self.client.login(username="pat", password="secret")
        self.assertEqual(self.client.get("/orders/").status_code, 200)
        self.assertEqual(self.client.get("/proposal/").status_code, 403)
