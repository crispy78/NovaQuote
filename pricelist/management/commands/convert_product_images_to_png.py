"""
Management command to convert product images to PNG and save under product_images/<uuid>.png.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from pricelist.models import Product


class Command(BaseCommand):
    help = "Convert product images to PNG and save under product_images/<uuid>.png."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be done, do not write files or update DB.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        media_root = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR))
        product_images_dir = media_root / "product_images"
        if not dry_run:
            product_images_dir.mkdir(parents=True, exist_ok=True)

        products = Product.objects.exclude(image="").exclude(image__isnull=True)
        converted = 0
        skipped = 0

        for product in products:
            old_rel = product.image.name
            old_path = media_root / old_rel

            if not old_path.exists():
                self.stdout.write(self.style.WARNING(f"Skip product pk={product.pk}: file not found {old_path}"))
                skipped += 1
                continue

            try:
                with Image.open(old_path) as img:
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")
                    new_name = f"product_images/{uuid.uuid4().hex}.png"
                    new_path = media_root / new_name
                    if not dry_run:
                        img.save(new_path, "PNG")
                        product.image = new_name
                        product.save(update_fields=["image"])
                        if old_path != new_path and old_path.exists():
                            old_path.unlink()
                converted += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Product pk={product.pk}: failed to convert: {e}")
                )
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Converted {converted} products."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped/failed {skipped} products."))
        if dry_run and converted:
            self.stdout.write("Dry run: no files written or DB updated.")
