"""Auto-number generators for SLURP ERP documents."""

from django.db import transaction
from django.utils import timezone

from erp_core.models import (
    BatchNumberSequence,
    Customer,
    CustomerNumberSequence,
    Invoice,
    InvoiceNumberSequence,
    Lot,
    LotNumberSequence,
    PONumberSequence,
    ProductionBatch,
    PurchaseOrder,
    SalesOrder,
    SalesOrderNumberSequence,
)


def generate_lot_number():
    today = timezone.now()
    year_prefix = today.strftime('%y')
    with transaction.atomic():
        sequence, _ = LotNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix, defaults={'sequence_number': 0}
        )
        sequence.sequence_number += 1
        sequence.save()
        lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
        retries = 0
        while Lot.objects.filter(lot_number=lot_number).exists() and retries < 10:
            sequence.sequence_number += 1
            sequence.save()
            lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
            retries += 1
    return lot_number


def generate_po_number():
    today = timezone.now()
    year_prefix = today.strftime('%y')
    with transaction.atomic():
        sequence, _ = PONumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix, defaults={'sequence_number': 0}
        )
        sequence.sequence_number += 1
        sequence.save()
        po_number = f"2{year_prefix}{sequence.sequence_number:04d}"
        retries = 0
        while PurchaseOrder.objects.filter(po_number=po_number).exists() and retries < 10:
            sequence.sequence_number += 1
            sequence.save()
            po_number = f"2{year_prefix}{sequence.sequence_number:04d}"
            retries += 1
    return po_number


def generate_sales_order_number():
    today = timezone.now()
    year_prefix = today.strftime('%y')
    with transaction.atomic():
        sequence, _ = SalesOrderNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix, defaults={'sequence_number': 0}
        )
        sequence.sequence_number += 1
        sequence.save()
        so_number = f"3{year_prefix}{sequence.sequence_number:04d}"
        retries = 0
        while SalesOrder.objects.filter(so_number=so_number).exists() and retries < 10:
            sequence.sequence_number += 1
            sequence.save()
            so_number = f"3{year_prefix}{sequence.sequence_number:04d}"
            retries += 1
    return so_number


def generate_invoice_number():
    today = timezone.now()
    year_prefix = today.strftime('%y')
    with transaction.atomic():
        sequence, _ = InvoiceNumberSequence.objects.select_for_update().get_or_create(
            year_prefix=year_prefix, defaults={'sequence_number': 0}
        )
        sequence.sequence_number += 1
        sequence.save()
        invoice_number = f"4{year_prefix}{sequence.sequence_number:04d}"
        retries = 0
        while Invoice.objects.filter(invoice_number=invoice_number).exists() and retries < 10:
            sequence.sequence_number += 1
            sequence.save()
            invoice_number = f"4{year_prefix}{sequence.sequence_number:04d}"
            retries += 1
    return invoice_number


def generate_customer_id():
    try:
        with transaction.atomic():
            sequence, _ = CustomerNumberSequence.objects.select_for_update().get_or_create(
                id=1, defaults={'sequence_number': 0}
            )
            sequence.sequence_number += 1
            sequence.save()
            customer_id = f"{sequence.sequence_number:03d}"
            retries = 0
            while Customer.objects.filter(customer_id=customer_id).exists() and retries < 10:
                sequence.sequence_number += 1
                sequence.save()
                customer_id = f"{sequence.sequence_number:03d}"
                retries += 1
            return customer_id
    except Exception:
        existing = Customer.objects.exclude(customer_id__isnull=True).exclude(customer_id='')
        max_id = 0
        for customer in existing:
            try:
                max_id = max(max_id, int(customer.customer_id))
            except (ValueError, TypeError):
                continue
        return f"{max_id + 1:03d}"


def generate_batch_number(batch_type='production'):
    today = timezone.now()
    date_prefix = today.strftime('%Y%m%d')
    prefix = 'REPACK' if batch_type == 'repack' else 'BATCH'
    with transaction.atomic():
        sequence, _ = BatchNumberSequence.objects.select_for_update().get_or_create(
            date_prefix=date_prefix, defaults={'sequence_number': 0}
        )
        sequence.sequence_number += 1
        sequence.save()
        batch_number = f"{prefix}-{date_prefix}-{sequence.sequence_number:03d}"
        retries = 0
        while ProductionBatch.objects.filter(batch_number=batch_number).exists() and retries < 10:
            sequence.sequence_number += 1
            sequence.save()
            batch_number = f"{prefix}-{date_prefix}-{sequence.sequence_number:03d}"
            retries += 1
    return batch_number
