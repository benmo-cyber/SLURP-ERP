"""Backfill SalesOrder.customer from customer_name when an exact (case-insensitive) Customer match exists.

Usage (from backend_django):
  python ../scripts/backfill_so_customer_fk.py
  python ../scripts/backfill_so_customer_fk.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")

import django

django.setup()

from erp_core.models import Customer, SalesOrder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    by_name: dict[str, list[Customer]] = defaultdict(list)
    for c in Customer.objects.all():
        by_name[(c.name or "").strip().lower()].append(c)

    orphans = SalesOrder.objects.filter(customer_id=None).order_by("id")
    linked = 0
    skipped = 0
    ambiguous = 0
    missing = 0

    for so in orphans:
        key = (so.customer_name or "").strip().lower()
        if not key:
            skipped += 1
            print(f"SKIP {so.so_number}: empty customer_name")
            continue
        matches = by_name.get(key) or []
        if len(matches) == 0:
            missing += 1
            print(f"MISS {so.so_number}: no customer for {so.customer_name!r}")
            continue
        if len(matches) > 1:
            ambiguous += 1
            print(f"AMBIG {so.so_number}: {so.customer_name!r} -> {[m.customer_id for m in matches]}")
            continue
        cust = matches[0]
        print(f"LINK {so.so_number}: {so.customer_name!r} -> {cust.customer_id} ({cust.name})")
        if not args.dry_run:
            so.customer = cust
            # Keep displayed name aligned with master
            if cust.name and so.customer_name != cust.name:
                so.customer_name = cust.name
            so.save(update_fields=["customer", "customer_name", "updated_at"])
        linked += 1

    print(
        f"\nDone. linked={linked} missing={missing} ambiguous={ambiguous} skipped={skipped}"
        + (" (dry-run)" if args.dry_run else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
