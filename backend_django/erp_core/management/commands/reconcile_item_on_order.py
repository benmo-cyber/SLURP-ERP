"""
Recalculate Item.on_order from open PO lines using native UOM helpers.

Example:
  python manage.py reconcile_item_on_order --dry-run
  python manage.py reconcile_item_on_order --sku M100 --apply
  python manage.py reconcile_item_on_order --apply
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from erp_core.buy_services import po_line_open_on_order_native
from erp_core.models import Item, PurchaseOrderItem


class Command(BaseCommand):
    help = "Reconcile Item.on_order from open issued/partial PO lines (native UOM)."

    def add_arguments(self, parser):
        parser.add_argument("--sku", type=str, default="", help="Limit to one SKU")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report diffs only (default unless --apply)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write corrected on_order values",
        )

    def handle(self, *args, **options):
        sku = (options.get("sku") or "").strip()
        apply = bool(options.get("apply"))
        # dry-run is default if not applying
        dry_run = (not apply) or bool(options.get("dry_run"))

        items = Item.objects.all()
        if sku:
            items = items.filter(sku=sku)
        items = list(items.order_by("sku", "id"))
        if not items:
            self.stdout.write(self.style.ERROR(f"No items found{f' for SKU {sku}' if sku else ''}."))
            return

        item_ids = [i.id for i in items]
        # Open POs that contribute to on_order: issued or partially received, not drop-ship
        open_lines = (
            PurchaseOrderItem.objects.filter(item_id__in=item_ids)
            .filter(purchase_order__drop_ship=False)
            .filter(purchase_order__status__in=["issued", "received"])
            .exclude(purchase_order__status="cancelled")
            .select_related("purchase_order", "item")
        )

        expected: dict[int, float] = defaultdict(float)
        for line in open_lines:
            po = line.purchase_order
            # Prefer latest revision per po_number when revision fields exist
            open_qty = po_line_open_on_order_native(line)
            if open_qty <= 1e-9:
                continue
            # Fully received POs marked received with zero open are skipped above
            expected[line.item_id] += open_qty

        # Also zero open for cancelled POs already handled by exclusion

        diffs = []
        for item in items:
            current = float(item.on_order or 0)
            want = round(float(expected.get(item.id, 0.0)), 6)
            if abs(current - want) > 0.01:
                diffs.append((item, current, want))

        self.stdout.write(
            f"Checked {len(items)} item(s); {len(diffs)} on_order mismatch(es)."
        )
        for item, current, want in diffs[:200]:
            self.stdout.write(
                f"  {item.sku} (id={item.id}): on_order={current} -> {want}"
            )
        if len(diffs) > 200:
            self.stdout.write(f"  ... and {len(diffs) - 200} more")

        if not diffs:
            self.stdout.write(self.style.SUCCESS("No corrections needed."))
            return

        if dry_run and not apply:
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to write."))
            return

        updated = 0
        for item, _current, want in diffs:
            item.on_order = want
            item.save(update_fields=["on_order"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated on_order on {updated} item(s)."))
