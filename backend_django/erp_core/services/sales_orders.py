"""Sales order workflow services."""

import re
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from erp_core.models import (
    Customer,
    InventoryTransaction,
    Invoice,
    InvoiceItem,
    Lot,
    SalesOrder,
    SalesOrderItem,
    SalesOrderLot,
)
from erp_core.services.inventory import WorkflowError
from erp_core.services.numbers import generate_invoice_number, generate_lot_number, generate_sales_order_number


def create_sales_order(*, customer, customer_reference_number='', items_data=None, **fields):
    so = SalesOrder.objects.create(
        so_number=generate_sales_order_number(),
        customer=customer,
        customer_name=customer.name,
        customer_reference_number=customer_reference_number,
        **fields,
    )
    for row in items_data or []:
        SalesOrderItem.objects.create(
            sales_order=so,
            item=row['item'],
            quantity_ordered=float(row['quantity_ordered']),
            unit_price=float(row.get('unit_price') or row['item'].price or 0),
            notes=row.get('notes', ''),
        )
    return so


def allocate_sales_order(sales_order, allocations):
    """
    allocations: list of dicts with keys item_id, lot_id, quantity
    """
    with transaction.atomic():
        for alloc in allocations:
            so_item = SalesOrderItem.objects.get(
                sales_order=sales_order, item_id=alloc['item_id']
            )
            SalesOrderLot.objects.filter(sales_order_item=so_item).delete()
            so_item.quantity_allocated = 0.0

            lot = Lot.objects.get(id=alloc['lot_id'], status='accepted')
            qty = float(alloc['quantity'])
            if lot.quantity_remaining < qty:
                raise WorkflowError(
                    f'Insufficient qty in lot {lot.lot_number}: '
                    f'available {lot.quantity_remaining}, requested {qty}'
                )
            SalesOrderLot.objects.create(
                sales_order_item=so_item, lot=lot, quantity_allocated=qty
            )
            so_item.quantity_allocated = qty
            so_item.save()

        if sales_order.items.filter(quantity_allocated__gt=0).exists():
            sales_order.status = 'allocated'
            sales_order.save()
    return sales_order


def ship_sales_order(sales_order, ship_date, invoice_date=None):
    invoice_date = invoice_date or ship_date
    for item in sales_order.items.all():
        if item.quantity_allocated < item.quantity_ordered:
            raise WorkflowError(
                f'{item.item.name} not fully allocated '
                f'({item.quantity_allocated}/{item.quantity_ordered}).'
            )

    with transaction.atomic():
        for so_item in sales_order.items.prefetch_related('allocated_lots'):
            for allocation in so_item.allocated_lots.all():
                lot = allocation.lot
                qty = allocation.quantity_allocated
                if lot.quantity_remaining < qty:
                    raise WorkflowError(f'Insufficient qty in lot {lot.lot_number}.')
                lot.quantity_remaining -= qty
                lot.save()
                InventoryTransaction.objects.create(
                    transaction_type='adjustment',
                    lot=lot,
                    quantity=-qty,
                    reference_number=sales_order.so_number,
                    notes=f'Shipped for SO {sales_order.so_number}',
                )
                so_item.quantity_shipped += qty
                so_item.save()

        sales_order.actual_ship_date = timezone.make_aware(
            datetime.combine(ship_date, datetime.min.time())
        )
        sales_order.status = 'shipped'
        sales_order.save()

        due_date = invoice_date
        if sales_order.customer and sales_order.customer.payment_terms:
            match = re.search(r'(\d+)', sales_order.customer.payment_terms)
            if match:
                due_date = invoice_date + timedelta(days=int(match.group(1)))

        subtotal = sum(
            (item.unit_price or 0) * item.quantity_ordered
            for item in sales_order.items.all()
        )
        invoice = Invoice.objects.create(
            invoice_number=generate_invoice_number(),
            sales_order=sales_order,
            invoice_date=invoice_date,
            due_date=due_date,
            status='draft',
            subtotal=subtotal,
            grand_total=subtotal,
            notes=f'Created from SO {sales_order.so_number}',
        )
        for so_item in sales_order.items.all():
            InvoiceItem.objects.create(
                invoice=invoice,
                sales_order_item=so_item,
                description=so_item.item.name,
                quantity=so_item.quantity_ordered,
                unit_price=so_item.unit_price or 0,
                total=(so_item.unit_price or 0) * so_item.quantity_ordered,
            )
    return sales_order, invoice
