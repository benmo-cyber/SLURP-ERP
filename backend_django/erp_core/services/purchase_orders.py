"""Purchase order workflow services."""

from django.utils import timezone

from erp_core.models import PurchaseOrder, PurchaseOrderItem
from erp_core.services.inventory import WorkflowError
from erp_core.services.numbers import generate_po_number


def create_purchase_order(*, vendor_name, items_data, **po_fields):
    po_number = generate_po_number()
    po = PurchaseOrder.objects.create(
        po_number=po_number,
        vendor_customer_name=vendor_name,
        po_type='vendor',
        status='draft',
        **po_fields,
    )
    subtotal = 0.0
    for row in items_data:
        item = row['item']
        qty = float(row['quantity_ordered'])
        unit_price = float(row.get('unit_price') or item.price or 0)
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            item=item,
            quantity_ordered=qty,
            unit_price=unit_price,
            notes=row.get('notes', ''),
        )
        subtotal += qty * unit_price
    po.subtotal = subtotal
    po.total = subtotal + (po.shipping_cost or 0) - (po.discount or 0)
    po.save()
    return po


def issue_purchase_order(po):
    if po.status != 'draft':
        raise WorkflowError(f'PO must be draft to issue (current: {po.status}).')
    po.status = 'issued'
    po.save()
    for po_item in po.items.select_related('item'):
        if po_item.item:
            po_item.item.on_order = (po_item.item.on_order or 0) + po_item.quantity_ordered
            po_item.item.save()
    return po


def receive_purchase_order(po):
    if po.status != 'issued':
        raise WorkflowError(f'PO must be issued to receive (current: {po.status}).')
    po.status = 'received'
    po.received_date = timezone.now()
    po.save()
    return po


def cancel_purchase_order(po):
    if po.status == 'completed':
        raise WorkflowError('Cannot cancel a completed purchase order.')
    if po.status == 'issued':
        for po_item in po.items.select_related('item'):
            if po_item.item:
                po_item.item.on_order = max(
                    0, (po_item.item.on_order or 0) - po_item.quantity_ordered
                )
                po_item.item.save()
    po.status = 'cancelled'
    po.save()
    return po


def revise_purchase_order(original_po):
    new_po = PurchaseOrder.objects.create(
        po_number=original_po.po_number,
        po_type=original_po.po_type,
        vendor_customer_name=original_po.vendor_customer_name,
        vendor_customer_id=original_po.vendor_customer_id,
        status='draft',
        revision_number=(original_po.revision_number or 0) + 1,
        original_po=original_po,
        order_number=original_po.order_number,
        expected_delivery_date=original_po.expected_delivery_date,
        required_date=original_po.required_date,
        shipping_terms=original_po.shipping_terms,
        shipping_method=original_po.shipping_method,
        ship_to_name=original_po.ship_to_name,
        ship_to_address=original_po.ship_to_address,
        ship_to_city=original_po.ship_to_city,
        ship_to_state=original_po.ship_to_state,
        ship_to_zip=original_po.ship_to_zip,
        ship_to_country=original_po.ship_to_country,
        vendor_address=original_po.vendor_address,
        vendor_city=original_po.vendor_city,
        vendor_state=original_po.vendor_state,
        vendor_zip=original_po.vendor_zip,
        vendor_country=original_po.vendor_country,
        subtotal=original_po.subtotal,
        discount=original_po.discount,
        shipping_cost=original_po.shipping_cost,
        total=original_po.total,
        coa_sds_email=original_po.coa_sds_email,
        notes=original_po.notes,
    )
    for oi in original_po.items.all():
        PurchaseOrderItem.objects.create(
            purchase_order=new_po,
            item=oi.item,
            quantity_ordered=oi.quantity_ordered,
            unit_price=oi.unit_price,
            notes=oi.notes,
        )
    if original_po.status == 'issued':
        for po_item in original_po.items.select_related('item'):
            if po_item.item:
                po_item.item.on_order = max(
                    0, (po_item.item.on_order or 0) - po_item.quantity_ordered
                )
                po_item.item.save()
        original_po.status = 'cancelled'
        original_po.save()
    return new_po
