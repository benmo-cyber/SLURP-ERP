"""
Reverse a checkout shipment: inventory, allocations, invoice/AR/journal, SO lines, then delete Shipment.

Used by management command remove_duplicate_shipment when a duplicate /ship/ created an extra Shipment.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List

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

    If allow_non_draft_invoice is False, refuses when linked invoice status != draft.
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
            if inv.status != 'draft' and not allow_non_draft_invoice:
                raise ValueError(
                    f'Invoice {inv.invoice_number} is status={inv.status}; '
                    'pass allow_non_draft_invoice=True only after manual review.'
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

        txns: List = list(
            InventoryTransaction.objects.filter(notes__icontains=needle).order_by('id')
        )
        txns_q: deque = deque(txns)

        ship_items = list(
            shipment.items.select_related('sales_order_item', 'sales_order_item__item').order_by('id')
        )

        for si in ship_items:
            so_item = si.sales_order_item
            target = float(si.quantity_shipped)
            acc = 0.0
            while acc < target - 0.02 and txns_q:
                t = txns_q.popleft()
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
                acc += amt

            if abs(acc - target) > 0.05:
                if acc < 0.02 and target > 0.02 and getattr(so, 'drop_ship', False):
                    # Virtual shipment line (no inventory transactions)
                    pass
                else:
                    raise ValueError(
                        f'Inventory txn mismatch reversing shipment {shipment_id} line {si.id}: '
                        f'restored {acc} vs line qty {target}'
                    )

            so_item.quantity_shipped -= target
            so_item.quantity_allocated += target
            so_item.save(update_fields=['quantity_shipped', 'quantity_allocated'])

        if txns_q:
            raise ValueError(f'Leftover inventory transactions for shipment {shipment_id}: {len(txns_q)}')

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
