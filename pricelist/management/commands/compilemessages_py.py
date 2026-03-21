"""
Compile .po translation files into .mo without requiring GNU gettext (msgfmt).

This is mainly for Windows dev environments where gettext tools are often missing.
Uses `polib` (pure Python) to read .po and write .mo files.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Compile locale/*/LC_MESSAGES/*.po to *.mo using pure Python (polib)."

    def add_arguments(self, parser):
        parser.add_argument(
            "-l",
            "--locale",
            action="append",
            dest="locales",
            default=[],
            help="Locale(s) to compile (e.g. -l nl). If omitted, compiles all locales under LOCALE_PATHS.",
        )
        parser.add_argument(
            "--domain",
            default="django",
            help="Translation domain (default: django).",
        )

    def handle(self, *args, **options):
        try:
            import polib  # type: ignore
        except Exception as e:
            raise CommandError(
                "Missing dependency 'polib'. Install it with: pip install polib"
            ) from e

        domain = options["domain"]
        locales = set(options["locales"] or [])
        locale_paths = [Path(p) for p in getattr(settings, "LOCALE_PATHS", [])]
        if not locale_paths:
            locale_paths = [Path(settings.BASE_DIR) / "locale"]

        compiled = 0
        missing = 0

        for base in locale_paths:
            if not base.exists():
                continue
            for locale_dir in base.iterdir():
                if not locale_dir.is_dir():
                    continue
                locale = locale_dir.name
                if locales and locale not in locales:
                    continue
                po_path = locale_dir / "LC_MESSAGES" / f"{domain}.po"
                mo_path = locale_dir / "LC_MESSAGES" / f"{domain}.mo"
                if not po_path.exists():
                    missing += 1
                    continue
                mo_path.parent.mkdir(parents=True, exist_ok=True)
                po = polib.pofile(str(po_path))
                po.save_as_mofile(str(mo_path))
                compiled += 1
                self.stdout.write(self.style.SUCCESS(f"Compiled {po_path} -> {mo_path}"))

        if compiled == 0:
            raise CommandError("No .po files found to compile.")
        if missing:
            self.stdout.write(self.style.WARNING(f"Skipped {missing} missing .po file(s)."))
        self.stdout.write(self.style.SUCCESS(f"Done. Compiled {compiled} locale(s)."))

