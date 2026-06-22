"""Inventory and lot workflow services."""

from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from erp_core.models import (
    CostMaster,
    InventoryTransaction,
    Item,
    Lot,
    ProductionBatchInput,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrderLot,
)
from erp_core.services.numbers import generate_lot_number


class WorkflowError(Exception):
    pass


def get_inventory_summary():
    """Return hierarchical SKU -> vendor inventory data for templates."""
    items = Item.objects.all()
    item_sales = {}
    for item_id in items.values_list('id', flat=True):
        total = SalesOrderLot.objects.filter(
            sales_order_item__item_id=item_id,
            sales_order_item__sales_order__status__in=['draft', 'allocated', 'shipped'],
        ).aggregate(total=Sum('quantity_allocated'))['total'] or 0.0
        item_sales[item_id] = total

    items_by_sku = {}
    for item in items:
        items_by_sku.setdefault(item.sku, []).append(item)

    summary = []
    for sku, sku_items in sorted(items_by_sku.items()):
        vendors = []
        for sku_item in sku_items:
            vendor_name = sku_item.vendor or 'Unknown'
            lots = Lot.objects.filter(item=sku_item, status='accepted')
            qty_remaining = sum(l.quantity_remaining for l in lots)
            on_order = sku_item.on_order or 0.0
            prod_alloc = ProductionBatchInput.objects.filter(
                lot__in=lots, batch__status__in=['in_progress', 'open', 'scheduled']
            ).aggregate(total=Sum('quantity_used'))['total'] or 0.0
            on_hold = sum(
                l.quantity_remaining for l in lots if l.status == 'on_hold' or l.on_hold
            )
            available = max(0.0, qty_remaining - prod_alloc - on_hold)
            vendors.append({
                'item': sku_item,
                'vendor': vendor_name,
                'lots': list(lots),
                'total_quantity': sum(l.quantity for l in lots) + on_order,
                'quantity_remaining': qty_remaining,
                'on_order': on_order,
                'allocated_to_sales': item_sales.get(sku_item.id, 0.0),
                'allocated_to_production': prod_alloc,
                'on_hold': on_hold,
                'available': available,
            })
        summary.append({
            'sku': sku,
            'description': sku_items[0].name,
            'item_type': sku_items[0].item_type,
            'vendors': vendors,
            'totals': {
                'total_quantity': sum(v['total_quantity'] for v in vendors),
                'quantity_remaining': sum(v['quantity_remaining'] for v in vendors),
                'on_order': sum(v['on_order'] for v in vendors),
                'available': sum(v['available'] for v in vendors),
            },
        })
    return summary


def check_in_lot(*, item, quantity, lot_status='accepted', vendor_lot_number='',
                 po_number='', freight_actual=None, expiration_date=None, short_reason=''):
    """Create a lot from receiving/check-in workflow."""
    if item.item_type == 'raw_material' and not vendor_lot_number.strip():
        raise WorkflowError('Vendor lot number is required for raw materials.')

    if item.item_type == 'finished_good':
        lot_number = generate_lot_number()
    elif item.item_type == 'raw_material':
        lot_number = vendor_lot_number.strip()
    else:
        lot_number = generate_lot_number()

    if lot_status == 'accepted':
        qty_remaining = quantity
    else:
        qty_remaining = 0

    lot = Lot.objects.create(
        lot_number=lot_number,
        vendor_lot_number=vendor_lot_number or None,
        item=item,
        quantity=quantity,
        quantity_remaining=qty_remaining,
        received_date=timezone.now(),
        expiration_date=expiration_date,
        status=lot_status,
        on_hold=(lot_status == 'on_hold'),
        freight_actual=freight_actual,
        po_number=po_number or None,
        short_reason=short_reason or None,
    )

    if lot_status == 'accepted':
        InventoryTransaction.objects.create(
            transaction_type='receipt', lot=lot, quantity=quantity,
        )
        if po_number:
            try:
                po = PurchaseOrder.objects.get(po_number=po_number)
                for po_item in po.items.all():
                    if po_item.item_id == item.id:
                        po_item.quantity_received += quantity
                        po_item.save()
                        item.on_order = max(0, (item.on_order or 0) - quantity)
                        item.save()
                        break
                all_received = all(
                    pi.quantity_received >= (pi.quantity_ordered - 0.01)
                    for pi in po.items.all()
                )
                if all_received and po.status == 'issued':
                    po.status = 'received'
                    po.save()
            except PurchaseOrder.DoesNotExist:
                pass
    return lot


def reverse_check_in(lot):
    """Reverse a lot check-in if lot has not been used."""
    if lot.quantity_remaining < lot.quantity:
        raise WorkflowError('Cannot reverse: lot has been partially or fully used.')

    lot_id = lot.id
    quantity = lot.quantity
    po_number = lot.po_number
    item_id = lot.item_id

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM erp_core_inventorytransaction WHERE lot_id = ? AND transaction_type = 'receipt' LIMIT 1",
            [lot_id],
        )
        if cursor.fetchone():
            InventoryTransaction.objects.create(
                transaction_type='adjustment', lot=lot, quantity=-quantity,
                notes='Reverse check-in',
            )

    if po_number:
        try:
            po = PurchaseOrder.objects.get(po_number=po_number)
            for po_item in po.items.filter(item_id=item_id):
                po_item.quantity_received = max(0, po_item.quantity_received - quantity)
                po_item.save()
            item = Item.objects.get(id=item_id)
            item.on_order = (item.on_order or 0) + quantity
            item.save()
        except (PurchaseOrder.DoesNotExist, Item.DoesNotExist):
            pass

    lot.delete()


def create_item_with_cost_master(data):
    """Create item and sync CostMaster entry."""
    if hasattr(data, 'items'):
        data = dict(data)
    for key in ('pack_size', 'price'):
        if data.get(key) == '' or data.get(key) is None:
            data[key] = None
    if data.get('vendor') == '':
        data['vendor'] = None
    if data.get('description') == '':
        data['description'] = None
    if 'on_order' not in data:
        data['on_order'] = 0

    sku = data['sku']
    vendor = data.get('vendor') or None
    if vendor and Item.objects.filter(sku=sku, vendor=vendor).exists():
        raise WorkflowError(f'Item SKU "{sku}" already exists for vendor "{vendor}".')

    item = Item.objects.create(**data)
    if item.vendor and data.get('price'):
        price = float(data['price'])
        uom = data.get('unit_of_measure', 'lbs')
        if uom == 'lbs':
            price_per_lb, price_per_kg = price, price * 2.20462
        elif uom == 'kg':
            price_per_kg, price_per_lb = price, price / 2.20462
        else:
            price_per_kg = price_per_lb = price
        CostMaster.objects.get_or_create(
            vendor_material=item.name,
            wwi_product_code=item.sku,
            vendor=item.vendor,
            defaults={
                'price_per_kg': price_per_kg,
                'price_per_lb': price_per_lb,
                'landed_cost_per_kg': price_per_kg,
                'landed_cost_per_lb': price_per_lb,
            },
        )
    return item
