"""
Reverse a checkout shipment: inventory, allocations, invoice/AR/journal, SO lines, then delete Shipment.

Used by management command remove_duplicate_shipment when a duplicate /ship/ created an extra Shipment.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from django.db import transaction

logger = logging.getLogger(__name__)

SHIPMENT_NOTE_MARKER = 'Shipment '


def _reverse_journal_balances(journal_entry) -> None:
    """Undo _update_account_balances for a posted journal entry."""
    from .models import AccountBalance

    fp = journal_entry.fiscal_period
    if not fp:
        return
    for line in journal_entry.lines.all():
        ab = AccountBalance.objects.filter(account=line.account, fiscal_period=fp).first()
        if not ab:
            continue
        if line.debit_credit == 'debit':
            ab.period_debits -= line.amount
        else:
            ab.period_credits -= line.amount
        if line.account.account_type in ['asset', 'expense']:
            ab.closing_balance = ab.opening_balance + ab.period_debits - ab.period_credits
        elif line.account.account_type in ['liability', 'equity', 'revenue']:
            ab.closing_balance = ab.opening_balance + ab.period_credits - ab.period_debits
        ab.save()


def _delete_invoice_finance_chain(invoice) -> None:
    """Remove invoice, AR, journal, and GL rows created for this shipment invoice."""
    from .models import AccountsReceivable, GeneralLedgerEntry, JournalEntryLine, InvoiceItem

    for ar in AccountsReceivable.objects.filter(invoice=invoice).select_related('journal_entry'):
        je = ar.journal_entry
        if je:
            _reverse_journal_balances(je)
            GeneralLedgerEntry.objects.filter(journal_entry=je).delete()
            JournalEntryLine.objects.filter(journal_entry=je).delete()
            je.delete()
        ar.delete()

    InvoiceItem.objects.filter(invoice=invoice).delete()
    invoice.delete()


def reverse_shipment(
    shipment_id: int,
    *,
    allow_non_draft_invoice: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Fully reverse one shipment. Raises ValueError if invariants fail.

    If allow_non_draft_invoice is False, refuses when a linked invoice is still active
    (e.g. sent/paid/overdue). Draft and cancelled invoices are always allowed: cancelled
    means voided in Finance and the row can be removed with the shipment.
    """
    from .models import (
        InventoryTransaction,
        Invoice,
        SalesOrder,
        SalesOrderLot,
        Shipment,
        ShipmentItem,
    )

    with transaction.atomic():
        shipment = (
            Shipment.objects.select_for_update()
            .select_related('sales_order')
            .get(pk=shipment_id)
        )
        so = SalesOrder.objects.select_for_update().get(pk=shipment.sales_order_id)

        needle = f'{SHIPMENT_NOTE_MARKER}{shipment.id}'
        invoices = list(
            Invoice.objects.select_for_update()
            .filter(sales_order=so)
            .filter(notes__icontains=needle)
        )
        for inv in invoices:
            if inv.status in ('draft', 'cancelled'):
                continue
            if not allow_non_draft_invoice:
                raise ValueError(
                    f'Invoice {inv.invoice_number} is status={inv.status}; '
                    'void it in Finance (cancelled) or pass allow_non_draft_invoice=True only after manual review.'
                )

        if dry_run:
            return {
                'dry_run': True,
                'shipment_id': shipment_id,
                'sales_order': so.so_number,
                'invoices': [i.invoice_number for i in invoices],
            }

        for inv in invoices:
            _delete_invoice_finance_chain(inv)

        # Match txns to shipment lines by lot ↔ SalesOrderLot for that line (checkout order ≠ ShipmentItem id order).
        all_txns: List = list(
            InventoryTransaction.objects.filter(notes__icontains=needle).select_related('lot').order_by('id')
        )
        used_ids: Set[int] = set()

        ship_items = list(
            shipment.items.select_related('sales_order_item', 'sales_order_item__item').order_by('id')
        )

        for si in ship_items:
            so_item = si.sales_order_item
            target = float(si.quantity_shipped)
            lot_ids = set(
                SalesOrderLot.objects.filter(sales_order_item=so_item).values_list('lot_id', flat=True)
            )
            line_txns = [t for t in all_txns if t.id not in used_ids and t.lot_id in lot_ids]
            line_txns.sort(key=lambda x: x.id)

            acc = 0.0
            for t in line_txns:
                if acc >= target - 0.02:
                    break
                amt = abs(float(t.quantity))
                lot = t.lot
                lot.quantity_remaining += amt
                lot.save(update_fields=['quantity_remaining'])
                sol, created = SalesOrderLot.objects.get_or_create(
                    sales_order_item=so_item,
                    lot=lot,
                    defaults={'quantity_allocated': amt},
                )
                if not created:
                    sol.quantity_allocated += amt
                    sol.save(update_fields=['quantity_allocated'])
                t.delete()
                used_ids.add(t.id)
                acc += amt

            if abs(acc - target) > 0.05:
                if acc < 0.02 and target > 0.02 and (
                    getattr(so, 'drop_ship', False) or not lot_ids
                ):
                    # Drop-ship / virtual line: no inventory movements for this ShipmentItem
                    pass
                else:
                    raise ValueError(
                        f'Inventory txn mismatch reversing shipment {shipment_id} line {si.id}: '
                        f'restored {acc} vs line qty {target}'
                    )

            so_item.quantity_shipped -= target
            so_item.quantity_allocated += target
            so_item.save(update_fields=['quantity_shipped', 'quantity_allocated'])

        leftover = [t for t in all_txns if t.id not in used_ids]
        if leftover:
            raise ValueError(
                f'Leftover inventory transactions for shipment {shipment_id}: {len(leftover)} '
                f'(could not match to shipment lines by lot)'
            )

        ShipmentItem.objects.filter(shipment=shipment).delete()
        shipment.delete()

        so.refresh_from_db()
        items = list(so.items.all())
        all_fully_shipped = all(
            (it.quantity_shipped or 0) >= (it.quantity_ordered or 0) for it in items
        )
        total_remaining_allocated = sum((it.quantity_allocated or 0) for it in items)
        if all_fully_shipped:
            so.status = 'completed'
        elif total_remaining_allocated > 0:
            so.status = 'ready_for_shipment'
        else:
            so.status = 'issued'
        so.save(update_fields=['status'])

        return {
            'ok': True,
            'removed_shipment_id': shipment_id,
            'sales_order': so.so_number,
            'new_status': so.status,
        }
