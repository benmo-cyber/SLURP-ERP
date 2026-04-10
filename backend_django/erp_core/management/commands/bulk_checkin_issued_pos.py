"""
Full check-in for all line items on issued vendor POs (remaining qty = ordered - received).

Creates lots, inventory receipts, CheckInLog rows, updates PO lines and on_order, sets PO to
received when fully received. Mirrors LotViewSet.create side effects.

CheckInLog records CoA, pest, and shipment flags as True (same as a compliant manual check-in);
initials default BM.

  python manage.py bulk_checkin_issued_pos --dry-run
  python manage.py bulk_checkin_issued_pos --initials BM
  python manage.py bulk_checkin_issued_pos --po 1001,1004 --carrier BM --use-expected-delivery-date
"""

from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from erp_core.models import (
    CheckInLog,
    InventoryTransaction,
    ItemPackSize,
    Lot,
    PurchaseOrder,
)
from erp_core.views import (
    create_ap_entry_from_po,
    generate_lot_number,
    log_lot_transaction,
    log_purchase_order_action,
)


def _default_pack_size(item):
    return ItemPackSize.objects.filter(item=item, is_default=True, is_active=True).first()


def _received_dt_from_expected_date(d):
    """DateField at noon in the active timezone."""
    naive = datetime.combine(d, time(12, 0, 0))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


class Command(BaseCommand):
    help = 'Fully check in all remaining quantities on issued vendor purchase orders.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--initials', type=str, default='BM', help='Check-in initials (default BM)')
        parser.add_argument(
            '--po',
            type=str,
            default='',
            help='Comma-separated PO numbers (e.g. 1001,1004). Optional; omit for all issued vendor POs.',
        )
        parser.add_argument(
            '--carrier',
            type=str,
            default='',
            help='Carrier stored on check-in log and PO when set (non-empty). Default: leave PO unchanged, use PO carrier on log.',
        )
        parser.add_argument(
            '--use-expected-delivery-date',
            action='store_true',
            help='Use expected_delivery_date (noon local) as received date on lots/logs/PO; requires date on PO.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        initials = (options['initials'] or 'BM').strip()[:50] or 'BM'
        po_filter_raw = (options['po'] or '').strip()
        carrier_override = (options['carrier'] or '').strip()[:255]
        use_expected = options['use_expected_delivery_date']

        po_numbers = None
        if po_filter_raw:
            po_numbers = [p.strip() for p in po_filter_raw.split(',') if p.strip()]

        qs = PurchaseOrder.objects.filter(po_type='vendor', status='issued').prefetch_related(
            'items__item'
        ).order_by('po_number')
        if po_numbers:
            qs = qs.filter(po_number__in=po_numbers)

        if po_numbers:
            found_issued = set(qs.values_list('po_number', flat=True))
            for num in po_numbers:
                if num not in found_issued:
                    po_obj = PurchaseOrder.objects.filter(po_number=num).first()
                    if not po_obj:
                        self.stdout.write(self.style.ERROR(f'PO {num}: not found in database'))
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'PO {num}: not included (status={po_obj.status}, '
                                f'po_type={po_obj.po_type}; need issued vendor PO)'
                            )
                        )

        total_lots = 0
        total_pos_done = 0
        skipped_pos = 0

        for po in qs:
            lines = list(po.items.all())
            if not lines:
                self.stdout.write(self.style.WARNING(f'PO {po.po_number}: no line items, skip'))
                skipped_pos += 1
                continue

            to_receive = []
            for line in lines:
                if not line.item_id:
                    self.stdout.write(
                        self.style.WARNING(f'PO {po.po_number}: line id={line.id} has no item, skip')
                    )
                    continue
                rem = float(line.quantity_ordered or 0) - float(line.quantity_received or 0)
                if rem > 0.01:
                    to_receive.append((line, rem))

            if not to_receive:
                self.stdout.write(f'PO {po.po_number}: already fully received, skip')
                skipped_pos += 1
                continue

            if use_expected and not po.expected_delivery_date:
                self.stdout.write(
                    self.style.ERROR(
                        f'PO {po.po_number}: --use-expected-delivery-date requires '
                        f'expected_delivery_date on the PO; skip'
                    )
                )
                skipped_pos += 1
                continue

            if dry:
                self.stdout.write(
                    self.style.WARNING(
                        f'Would check in PO {po.po_number}: {len(to_receive)} line(s) '
                        + ', '.join(f'{ln.item.sku}={qty:g}' for ln, qty in to_receive)
                        + (f' (received_dt=expected {po.expected_delivery_date})' if use_expected else '')
                    )
                )
                total_lots += len(to_receive)
                total_pos_done += 1
                continue

            with transaction.atomic():
                if use_expected:
                    received_dt = _received_dt_from_expected_date(po.expected_delivery_date)
                else:
                    received_dt = timezone.now()

                if carrier_override:
                    po.carrier = carrier_override
                    po.save(update_fields=['carrier'])

                carrier_val = carrier_override or ((po.carrier or '').strip() if po.carrier else '')

                last_lot = None
                for po_item, qty in to_receive:
                    item = po_item.item
                    lot_number = generate_lot_number()
                    vendor_lot = f'{initials}-AUTO-{po.po_number}-{item.sku}'[:100]
                    ps = _default_pack_size(item)

                    lot = Lot.objects.create(
                        lot_number=lot_number,
                        vendor_lot_number=vendor_lot,
                        item=item,
                        pack_size=ps,
                        quantity=qty,
                        quantity_remaining=qty,
                        received_date=received_dt,
                        expiration_date=None,
                        status='accepted',
                        on_hold=False,
                        po_number=po.po_number,
                        freight_actual=None,
                    )

                    txn = InventoryTransaction.objects.create(
                        transaction_type='receipt',
                        lot=lot,
                        quantity=qty,
                    )

                    log_lot_transaction(
                        lot=lot,
                        quantity_before=0.0,
                        quantity_change=qty,
                        transaction_type='receipt',
                        reference_number=po.po_number,
                        reference_type='po_number',
                        transaction_id=txn.id,
                        purchase_order_id=po.id,
                        notes=f'Bulk check-in initials {initials} - PO {po.po_number}',
                    )

                    po_item.quantity_received = float(po_item.quantity_received or 0) + qty
                    po_item.save(update_fields=['quantity_received'])

                    item.on_order = max(0.0, float(item.on_order or 0) - qty)
                    item.save(update_fields=['on_order'])

                    CheckInLog.objects.create(
                        lot=lot,
                        lot_number=lot.lot_number or '',
                        item_id=item.id,
                        item_sku=item.sku,
                        item_name=item.name,
                        item_type=item.item_type,
                        item_unit_of_measure=item.unit_of_measure,
                        po_number=po.po_number,
                        vendor_name=getattr(item, 'vendor', None) or '',
                        received_date=received_dt,
                        manufacture_date=None,
                        expiration_date=None,
                        vendor_lot_number=vendor_lot,
                        quantity=qty,
                        quantity_unit=item.unit_of_measure,
                        status='accepted',
                        coa=True,
                        prod_free_pests=True,
                        carrier_free_pests=True,
                        shipment_accepted=True,
                        initials=initials,
                        carrier=carrier_val,
                        freight_actual=None,
                        notes=(
                            f'Automated full check-in (management command). Initials {initials}. '
                            'CoA / pest / shipment flags set True to match required check-in attestations.'
                        ),
                        checked_in_by='bulk_checkin_issued_pos',
                    )

                    log_purchase_order_action(
                        po,
                        'partial_check_in',
                        lot=lot,
                        notes=f'Bulk check-in: {qty:g} {item.sku} (initials {initials})',
                    )
                    last_lot = lot
                    total_lots += 1

                all_received = True
                po.refresh_from_db()
                for pit in po.items.all():
                    if float(pit.quantity_received or 0) < float(pit.quantity_ordered or 0) - 0.01:
                        all_received = False
                        break

                if all_received:
                    po.status = 'received'
                    po.received_date = received_dt
                    po.save()
                    log_purchase_order_action(
                        po,
                        'completed',
                        lot=last_lot,
                        notes=f'All items fully received (bulk check-in, initials {initials})',
                    )
                    try:
                        create_ap_entry_from_po(po)
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f'PO {po.po_number}: create_ap_entry_from_po: {e}')
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'PO {po.po_number}: checked in {len(to_receive)} line(s); '
                        f'status={po.status}'
                    )
                )
                total_pos_done += 1

        self.stdout.write('')
        self.stdout.write(
            f'Summary: POs processed={total_pos_done}, lots created={total_lots}, '
            f'skipped/unchanged POs={skipped_pos}, dry_run={dry}'
        )
