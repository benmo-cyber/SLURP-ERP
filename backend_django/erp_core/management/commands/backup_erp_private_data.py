import json
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from erp_core.sample_xml_import import get_private_sample_data_dir


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).parent.resolve()


def _backup_dir() -> Path:
    d = _repo_root() / "data" / "private_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Command(BaseCommand):
    help = (
        "Write a private zip of wwi_erp.db + media/ (and optionally JSON dumpdata) under data/private_backups/. "
        "Run before git push; that folder is gitignored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Also write erp_dumpdata_<timestamp>.json (for non-SQLite restore; see README).",
        )

    def handle(self, *args, **options):
        want_json = options["json"]
        ts = timezone.now().strftime("%Y%m%d_%H%M%S")
        out_dir = _backup_dir()
        db_path = Path(settings.DATABASES["default"]["NAME"])
        media_root = Path(settings.MEDIA_ROOT)

        zip_path = out_dir / f"erp_data_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if db_path.is_file():
                zf.write(db_path, arcname="wwi_erp.db")
                self.stdout.write(self.style.SUCCESS(f"Added database: {db_path}"))
            else:
                self.stdout.write(
                    self.style.WARNING(f"Database file not found (skipped): {db_path}")
                )

            if media_root.is_dir():
                n = 0
                for f in media_root.rglob("*"):
                    if f.is_file() and f.name != ".gitkeep":
                        arc = Path("media") / f.relative_to(media_root)
                        zf.write(f, arcname=str(arc).replace("\\", "/"))
                        n += 1
                self.stdout.write(self.style.SUCCESS(f"Added {n} file(s) from {media_root}"))
            else:
                self.stdout.write(f"No media folder yet: {media_root}")

        self.stdout.write(self.style.SUCCESS(f"\nBackup zip: {zip_path}"))

        if want_json:
            json_path = out_dir / f"erp_dumpdata_{ts}.json"
            with open(json_path, "w", encoding="utf-8") as fp:
                call_command(
                    "dumpdata",
                    "erp_core",
                    indent=2,
                    natural_foreign=True,
                    natural_primary=True,
                    stdout=fp,
                )
            self.stdout.write(self.style.SUCCESS(f"JSON dump: {json_path}"))

        self.stdout.write(
            "\nCopy the zip (and JSON if any) to safe storage. "
            "They are gitignored; they will not be pushed with code.\n"
            "Verify: git status (should not list wwi_erp.db, media files, or these backups).\n"
        )
