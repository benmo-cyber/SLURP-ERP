"""
Fix denormalized vendor strings after a rename (or run once if items still show the old name).

Usage:
  python manage.py cascade_vendor_name "Old Vendor LLC" "New Vendor LLC"

Updates Item.vendor, CostMaster.vendor, VendorPricing, AP, PO vendor_customer_name, orphaned rows.
"""
from django.core.management.base import BaseCommand

from erp_core.vendor_rename import cascade_vendor_name_change


class Command(BaseCommand):
    help = "Update denormalized vendor name strings from OLD to NEW (matches Vendor rename behavior)."

    def add_arguments(self, parser):
        parser.add_argument("old_name", type=str, help="Previous vendor name as stored on items (exact match)")
        parser.add_argument("new_name", type=str, help="Current vendor name (must match Vendor.name)")

    def handle(self, *args, **options):
        old_name = (options["old_name"] or "").strip()
        new_name = (options["new_name"] or "").strip()
        counts = cascade_vendor_name_change(old_name, new_name)
        if not counts:
            self.stdout.write(self.style.WARNING("Nothing updated (names empty or identical)."))
            return
        self.stdout.write(self.style.SUCCESS(f"Updated rows: {counts}"))
