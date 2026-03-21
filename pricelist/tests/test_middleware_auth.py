"""Authentication: frontend routes require login."""

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class LoginRequiredMiddlewareTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonymous_redirects_from_price_list(self):
        r = self.client.get("/price-list/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_anonymous_redirects_from_contacts(self):
        r = self.client.get("/contacts/suppliers/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_anonymous_can_access_login(self):
        r = self.client.get("/accounts/login/")
        self.assertEqual(r.status_code, 200)

    def test_authenticated_can_access_price_list(self):
        User.objects.create_user("alice", "a@example.com", "secret123")
        self.client.login(username="alice", password="secret123")
        r = self.client.get("/price-list/")
        self.assertEqual(r.status_code, 200)
