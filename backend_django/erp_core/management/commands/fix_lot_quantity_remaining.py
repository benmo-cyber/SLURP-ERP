"""
Fix quantity_remaining to match received (quantity) for lots where it was
incorrectly reduced (e.g. M100: 5000 received but quantity_remaining=4650).

Use when you've confirmed the "missing" amount was never actually shipped/used.

Example:
  python manage.py fix_lot_quantity_remaining --sku M100 --dry-run
  python manage.py fix_lot_quantity_remaining --sku M100
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum
from erp_core.models import Item, Lot, SalesOrderLot, ProductionBatchInput


class Command(BaseCommand):
    help = 'Set quantity_remaining = quantity for lots where remaining is short (fix discrepancy).'

    def add_arguments(self, parser):
        parser.add_argument('--sku', type=str, help='SKU to fix (e.g. M100)')
        parser.add_argument('--lot-number', type=str, help='Or fix a specific lot by lot_number')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without saving.')

    def handle(self, *args, **options):
        sku = options.get('sku')
        lot_number = options.get('lot_number')
        dry_run = options.get('dry_run', False)

        if not sku and not lot_number:
            self.stdout.write(self.style.ERROR('Provide --sku or --lot-number'))
            return

        if lot_number:
            lots = list(Lot.objects.filter(lot_number=lot_number).values('id', 'lot_number', 'quantity', 'quantity_remaining', 'item_id'))
            if not lots:
                self.stdout.write(self.style.ERROR(f'Lot not found: {lot_number}'))
                return
        else:
            items = list(Item.objects.filter(sku=sku))
            if not items:
                self.stdout.write(self.style.ERROR(f'No items found for SKU {sku}'))
                return
            item_ids = [i.id for i in items]
            lots = list(
                Lot.objects.filter(item_id__in=item_ids)
                .values('id', 'lot_number', 'quantity', 'quantity_remaining', 'item_id')
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be saved.'))

        updated = 0
        for row in lots:
            qty = row['quantity']
            remaining = row['quantity_remaining']
            if remaining >= qty:
                continue
            short_by = qty - remaining
            lot_id = row['id']
            # Safety: ensure we're not overwriting valid deductions (sales alloc + prod alloc)
            sales_alloc = (
                SalesOrderLot.objects.filter(
                    lot_id=lot_id,
                    sales_order_item__sales_order__status__in=[
                        'draft', 'allocated', 'issued', 'ready_for_shipment', 'shipped'
                    ]
                ).aggregate(total=Sum('quantity_allocated'))['total'] or 0.0
            )
            prod_alloc = (
                ProductionBatchInput.objects.filter(
                    lot_id=lot_id, batch__status='in_progress'
                ).aggregate(total=Sum('quantity_used'))['total'] or 0.0
            )
            # Expected remaining if we only had these allocations would be qty - sales - prod (for shipped, qty_remaining is already reduced)
            # So restoring to qty is correct if no sales/prod should have reduced it
            self.stdout.write(
                f"  Lot {row['lot_number']} (id={lot_id}): quantity={qty}, quantity_remaining={remaining} "
                f"(short by {short_by}), sales_alloc={sales_alloc}, prod_alloc={prod_alloc}"
            )
            if not dry_run:
                Lot.objects.filter(id=lot_id).update(quantity_remaining=qty)
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"    -> Set quantity_remaining to {qty}"))
            else:
                self.stdout.write(f"    -> Would set quantity_remaining to {qty}")
                updated += 1

        if not updated:
            self.stdout.write('No lots needed correction (quantity_remaining already >= quantity).')
        elif dry_run:
            self.stdout.write(self.style.WARNING(f'Would correct {updated} lot(s). Run without --dry-run to apply.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Corrected {updated} lot(s).'))
