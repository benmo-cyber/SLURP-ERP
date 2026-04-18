"""
Export the SQLite database to human-readable files: one CSV per table + an index.

  python manage.py export_sqlite_readable
  python manage.py export_sqlite_readable --output-dir C:\\exports\\my_dump

Default output: ../../data/private_backups/sqlite_readable_<timestamp>/ (gitignored).
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).parent.resolve()


def _default_out_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    d = _repo_root() / "data" / "private_backups" / f"sqlite_readable_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cell_for_csv(value):
    if value is None:
        return ""
    if isinstance(value, (bytes, memoryview)):
        raw = bytes(value)
        return f"<BLOB {len(raw)} bytes>"
    return value


class Command(BaseCommand):
    help = "Export SQLite to per-table CSV files plus INDEX.md (human-readable)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="Destination folder (default: data/private_backups/sqlite_readable_<UTC timestamp>).",
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])
        if not db_path.is_file():
            self.stderr.write(self.style.ERROR(f"Database not found: {db_path}"))
            return

        out_dir = Path(options["output_dir"]).resolve() if options["output_dir"] else _default_out_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
            tables = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

        index_lines = [
            "# SQLite export (human-readable)",
            "",
            f"- **Source:** `{db_path}`",
            f"- **Exported (UTC):** {datetime.now(timezone.utc).isoformat()}",
            f"- **Tables:** {len(tables)}",
            "",
            "| Table | Rows | File |",
            "|-------|------|------|",
        ]

        total_rows = 0
        for name in tables:
            safe_name = name.replace("/", "_")
            csv_path = out_dir / f"{safe_name}.csv"
            n = self._export_table(db_path, name, csv_path)
            total_rows += n
            index_lines.append(f"| `{name}` | {n} | `{csv_path.name}` |")

        index_lines.extend(
            [
                "",
                f"**Total rows (all tables):** {total_rows}",
                "",
                "Each `.csv` file is UTF-8. Open in Excel, LibreOffice, or a text editor.",
                "Binary columns appear as `<BLOB n bytes>`.",
            ]
        )

        index_path = out_dir / "INDEX.md"
        index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Wrote {len(tables)} table(s) + INDEX.md under:\n  {out_dir}"))

    def _export_table(self, db_path: Path, table: str, csv_path: Path) -> int:
        conn = sqlite3.connect(str(db_path))
        try:
            q = 'SELECT * FROM "' + table.replace('"', '""') + '"'
            cur = conn.execute(q)
            colnames = [d[0] for d in cur.description]
            n = 0
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as fp:
                w = csv.writer(fp)
                w.writerow(colnames)
                for row in cur:
                    w.writerow([_cell_for_csv(row[i]) for i in range(len(colnames))])
                    n += 1
            return n
        finally:
            conn.close()
