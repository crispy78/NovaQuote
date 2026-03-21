# Rename product_afbeeldingen directory and update Product.afbeelding paths to product_images

import os

from django.db import migrations
from django.conf import settings


def rename_folder_and_update_paths(apps, schema_editor):
    Product = apps.get_model("pricelist", "Product")
    media_root = getattr(settings, "MEDIA_ROOT", None) or settings.BASE_DIR
    old_dir = os.path.join(media_root, "product_afbeeldingen")
    new_dir = os.path.join(media_root, "product_images")

    if os.path.isdir(old_dir) and not os.path.isdir(new_dir):
        os.rename(old_dir, new_dir)

    prefix = "product_afbeeldingen/"
    for product in Product.objects.exclude(afbeelding="").exclude(afbeelding__isnull=True):
        path = product.afbeelding.name if hasattr(product.afbeelding, "name") else str(product.afbeelding)
        if path and path.startswith(prefix):
            product.afbeelding = "product_images/" + path[len(prefix) :]
            product.save(update_fields=["afbeelding"])


def reverse_rename_folder_and_paths(apps, schema_editor):
    Product = apps.get_model("pricelist", "Product")
    media_root = getattr(settings, "MEDIA_ROOT", None) or settings.BASE_DIR
    old_dir = os.path.join(media_root, "product_afbeeldingen")
    new_dir = os.path.join(media_root, "product_images")

    if os.path.isdir(new_dir) and not os.path.isdir(old_dir):
        os.rename(new_dir, old_dir)

    prefix = "product_images/"
    for product in Product.objects.exclude(afbeelding="").exclude(afbeelding__isnull=True):
        path = product.afbeelding.name if hasattr(product.afbeelding, "name") else str(product.afbeelding)
        if path and path.startswith(prefix):
            product.afbeelding = "product_afbeeldingen/" + path[len(prefix) :]
            product.save(update_fields=["afbeelding"])


class Migration(migrations.Migration):

    dependencies = [
        ("pricelist", "0031_algemene_instellingen_taal"),
    ]

    operations = [
        migrations.RunPython(rename_folder_and_update_paths, reverse_rename_folder_and_paths),
    ]
