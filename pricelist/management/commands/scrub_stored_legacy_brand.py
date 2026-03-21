"""Re-run stored-string normalization (legacy vendor token → NovaQuote in text/JSON fields)."""

from django.core.management.base import BaseCommand

from pricelist.db_scrub import replace_stored_legacy_brand_segments


class Command(BaseCommand):
    help = (
        "Replace legacy vendor substrings in CharField, TextField, and JSONField values across all models. "
        "Safe to run multiple times."
    )

    def handle(self, *args, **options):
        n = replace_stored_legacy_brand_segments()
        self.stdout.write(self.style.SUCCESS(f"Updated {n} row(s)."))
