"""Finance and calendar helper services."""

from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from erp_core.models import (
    Account,
    Invoice,
    Lot,
    ProductionBatch,
    PurchaseOrder,
    SalesOrder,
)


def get_aging_report():
    today = timezone.now().date()
    invoices = Invoice.objects.exclude(status__in=['paid', 'cancelled']).select_related(
        'sales_order__customer'
    )
    buckets = {'current': [], '1-30': [], '31-60': [], '61-90': [], '90+': []}
    for inv in invoices:
        days = (today - inv.due_date).days
        if days <= 0:
            buckets['current'].append(inv)
        elif days <= 30:
            buckets['1-30'].append(inv)
        elif days <= 60:
            buckets['31-60'].append(inv)
        elif days <= 90:
            buckets['61-90'].append(inv)
        else:
            buckets['90+'].append(inv)
    return buckets


def get_chart_of_accounts():
    accounts = Account.objects.filter(is_active=True).order_by('account_number')
    grouped = {}
    for acct in accounts:
        grouped.setdefault(acct.get_account_type_display(), []).append(acct)
    return grouped


def get_calendar_events(start_date, end_date, event_types=None):
    events = []
    types = event_types or ['shipments', 'receipts', 'production']

    if 'shipments' in types:
        for so in SalesOrder.objects.filter(
            Q(expected_ship_date__date__gte=start_date, expected_ship_date__date__lte=end_date)
            | Q(actual_ship_date__date__gte=start_date, actual_ship_date__date__lte=end_date)
        ):
            d = (so.actual_ship_date or so.expected_ship_date)
            if d:
                events.append({
                    'date': d.date() if hasattr(d, 'date') else d,
                    'title': f'Ship: {so.so_number}',
                    'type': 'shipment',
                })

    if 'receipts' in types:
        for po in PurchaseOrder.objects.filter(
            expected_delivery_date__gte=start_date,
            expected_delivery_date__lte=end_date,
        ):
            events.append({
                'date': po.expected_delivery_date,
                'title': f'PO Delivery: {po.po_number}',
                'type': 'receipt',
            })
        for lot in Lot.objects.filter(
            received_date__date__gte=start_date,
            received_date__date__lte=end_date,
        ):
            events.append({
                'date': lot.received_date.date(),
                'title': f'Received: {lot.lot_number}',
                'type': 'receipt',
            })

    if 'production' in types:
        for batch in ProductionBatch.objects.filter(
            production_date__date__gte=start_date,
            production_date__date__lte=end_date,
        ):
            events.append({
                'date': batch.production_date.date(),
                'title': f'Batch: {batch.batch_number}',
                'type': 'production',
            })

    return sorted(events, key=lambda e: e['date'])
