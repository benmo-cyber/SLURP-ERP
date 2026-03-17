"""
Reconcile inventory for a SKU: show per-lot and item-level breakdown so you can
verify Available = Received - Alloc. Sales - Alloc. Prod - On Hold.

Example (trace M100 discrepancy):
  python manage.py reconcile_inventory_sku --sku M100
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum
from erp_core.models import Item, Lot, SalesOrderLot, ProductionBatchInput


class Command(BaseCommand):
    help = 'Reconcile inventory for a SKU: lot-level and item-level breakdown.'

    def add_arguments(self, parser):
        parser.add_argument('--sku', type=str, default='M100', help='SKU to reconcile (default: M100)')

    def handle(self, *args, **options):
        sku = options['sku']
        items = list(Item.objects.filter(sku=sku))
        if not items:
            self.stdout.write(self.style.ERROR(f'No items found for SKU {sku}'))
            return
        item_ids = [i.id for i in items]
        # Use values() to avoid loading relations (e.g. pack_size) that might be missing in DB
        lot_rows = list(
            Lot.objects.filter(item_id__in=item_ids, quantity_remaining__gt=0)
            .order_by('id')
            .values('id', 'lot_number', 'quantity', 'quantity_remaining', 'quantity_on_hold', 'item_id')
        )
        if not lot_rows:
            self.stdout.write(f'No lots with quantity_remaining > 0 for SKU {sku}.')
            return

        self.stdout.write(f'\n=== Inventory reconciliation for SKU: {sku} ===\n')
        total_qty = 0.0
        total_remaining = 0.0
        total_on_hold = 0.0
        total_sales_alloc = 0.0
        total_prod_alloc = 0.0

        for row in lot_rows:
            lot_id = row['id']
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
            qty_hold = row.get('quantity_on_hold') or 0.0
            qty_remaining = row['quantity_remaining']
            qty_received = row['quantity']
            effective_remaining = max(0.0, qty_remaining - sales_alloc)
            available_lot = max(0.0, effective_remaining - qty_hold - prod_alloc)

            total_qty += qty_received
            total_remaining += qty_remaining
            total_on_hold += qty_hold
            total_sales_alloc += sales_alloc
            total_prod_alloc += prod_alloc

            self.stdout.write(
                f"  Lot {row['lot_number']} (id={lot_id}): received={qty_received}, "
                f"quantity_remaining={qty_remaining}, quantity_on_hold={qty_hold}, "
                f"sales_alloc={sales_alloc}, prod_alloc={prod_alloc} -> available_from_lot={available_lot:.2f}"
            )

        # Item-level allocated_to_sales (how the inventory view computes it)
        item_sales = 0.0
        for item in items:
            item_sales += (
                SalesOrderLot.objects.filter(
                    sales_order_item__item_id=item.id,
                    sales_order_item__sales_order__status__in=[
                        'draft', 'allocated', 'issued', 'ready_for_shipment', 'shipped'
                    ]
                ).aggregate(total=Sum('quantity_allocated'))['total'] or 0.0
            )

        self.stdout.write(f'\n  Totals: received={total_qty}, quantity_remaining={total_remaining}, '
                          f'quantity_on_hold={total_on_hold}, sales_alloc={total_sales_alloc}, prod_alloc={total_prod_alloc}')
        self.stdout.write(f'  Item-level allocated_to_sales (for this SKU items): {item_sales}')
        # Same formula as inventory view
        quantity_remaining_display = 0.0
        for row in lot_rows:
            sales = (
                SalesOrderLot.objects.filter(
                    lot_id=row['id'],
                    sales_order_item__sales_order__status__in=[
                        'draft', 'allocated', 'issued', 'ready_for_shipment', 'shipped'
                    ]
                ).aggregate(total=Sum('quantity_allocated'))['total'] or 0.0
            )
            quantity_remaining_display += max(0.0, row['quantity_remaining'] - sales)
        available = max(0.0, quantity_remaining_display - total_on_hold - total_prod_alloc)
        self.stdout.write(f'  quantity_remaining (display, after sales alloc) = {quantity_remaining_display}')
        self.stdout.write(f'  Available = quantity_remaining - on_hold - prod_alloc = {available}')
        if total_qty and total_remaining < total_qty and total_sales_alloc == 0:
            self.stdout.write(self.style.WARNING(
                f'  Note: quantity_remaining ({total_remaining}) < received ({total_qty}). '
                f'Difference {total_qty - total_remaining} was already deducted (e.g. shipped or adjusted).'
            ))
        self.stdout.write('')
