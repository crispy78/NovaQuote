"""
Create or update RBAC demo accounts and Frontend role templates (non-destructive).

Does not flush the database. Use after ``migrate`` to try Sales / Catalog manager /
Procurement on the frontend without loading full ``seed_demo`` data.

Usage:
    python manage.py seed_rbac_demo_users
    python manage.py seed_rbac_demo_users --password demo --reset-password
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from pricelist.rbac_demo_seed import DEMO_USER_SPECS, ensure_frontend_roles_and_demo_users


class Command(BaseCommand):
    help = "Ensure Frontend roles and demo users sales / catalog / buyer exist (does not wipe data)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="demo",
            help="Password for newly created demo users (default: demo).",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Also set the password for existing sales, catalog, and buyer users.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        reset = options["reset_password"]
        ensure_frontend_roles_and_demo_users(password, admin_user=None, reset_demo_passwords=reset)
        self.stdout.write(self.style.SUCCESS("Frontend roles are up to date."))
        self.stdout.write("")
        self.stdout.write("Log in at /accounts/login/ with:")
        self.stdout.write("")
        for username, slug in DEMO_USER_SPECS:
            role_label = slug.replace("_", " ").title()
            self.stdout.write(f"  - {username} -> {role_label}")
        self.stdout.write("")
        if reset:
            self.stdout.write(self.style.WARNING(f"Password for all three users set to: {password!r}"))
        else:
            self.stdout.write(
                f"New users get password {password!r}. "
                "Existing users keep their password unless you pass --reset-password."
            )
        self.stdout.write("")
        self.stdout.write("Use your superuser (or admin from seed_demo) for full access.")
