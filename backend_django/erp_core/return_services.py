"""
Customer return / credit-memo flow (post-issue or paid AR).

Does not reverse shipment history. Creates a credit invoice, applies open AR,
restocks inventory into a return lot, and posts Dr revenue / Cr AR (not cash).
Refunds of already-paid bills stay manual (Mark as paid / bank confirmation).
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import (
    Account,
    AccountsReceivable,
    FiscalPeriod,
    GeneralLedgerEntry,
    InventoryTransaction,
    Invoice,
    InvoiceItem,
    JournalEntryLine,
    Lot,
    Payment,
    SalesOrder,
    SalesOrderItem,
)
from .sell_services import SellFlowError


def _ensure_fiscal_period(ref_date):
    from datetime import date

    fiscal_period = FiscalPeriod.objects.filter(
        start_date__lte=ref_date, end_date__gte=ref_date
    ).first()
    if fiscal_period:
        return fiscal_period
    year = ref_date.year
    fiscal_period, _ = FiscalPeriod.objects.get_or_create(
        period_name=f"{year}-01",
        defaults={"start_date": date(year, 1, 1), "end_date": date(year, 12, 31)},
    )
    return fiscal_period


def _post_balanced_je(journal_entry, *, reference_type: str) -> None:
    from .views import _update_account_balances

    total_debits = sum(
        line.amount for line in journal_entry.lines.filter(debit_credit="debit")
    )
    total_credits = sum(
        line.amount for line in journal_entry.lines.filter(debit_credit="credit")
    )
    if abs(total_debits - total_credits) > 0.01:
        return
    for line in journal_entry.lines.all():
        GeneralLedgerEntry.objects.create(
            journal_entry=journal_entry,
            journal_entry_line=line,
            account=line.account,
            fiscal_period=journal_entry.fiscal_period,
            entry_date=journal_entry.entry_date,
            description=line.description or journal_entry.description,
            debit_credit=line.debit_credit,
            amount=line.amount,
            reference_number=journal_entry.reference_number,
            reference_type=reference_type,
        )
    journal_entry.status = "posted"
    journal_entry.save(update_fields=["status"])
    _update_account_balances(journal_entry)


def _create_credit_application_je(
    *,
    amount: float,
    customer_name: str,
    credit_invoice: Invoice,
    ar_entry: AccountsReceivable,
    payment: Payment,
):
    from .views import create_journal_entry_allocating_number

    today = timezone.now().date()
    ref_date = payment.payment_date or today
    fiscal_period = _ensure_fiscal_period(ref_date)
    if fiscal_period.is_closed:
        return None

    ar_account = ar_entry.account
    if not ar_account:
        ar_account = Account.objects.filter(account_number="1100").first()
        if not ar_account:
            ar_account = Account.objects.filter(
                account_type="asset", account_number__startswith="11"
            ).first()
        if not ar_account:
            ar_account = Account.objects.create(
                account_number="1100",
                name="Accounts Receivable",
                account_type="asset",
                description="",
            )

    revenue_account = Account.objects.filter(account_number="4000").first()
    if not revenue_account:
        revenue_account = Account.objects.filter(account_type="revenue").first()
        if not revenue_account:
            revenue_account = Account.objects.create(
                account_number="4000",
                name="Sales - Finished Goods",
                account_type="revenue",
                description="Parent income account",
            )

    journal_entry = create_journal_entry_allocating_number(
        ref_date,
        entry_date=ref_date,
        description=(
            f"Credit memo {credit_invoice.invoice_number} "
            f"applied to AR (invoice {ar_entry.invoice.invoice_number if ar_entry.invoice else 'N/A'})"
        ),
        reference_number=credit_invoice.invoice_number,
        reference_type="credit_memo",
        status="draft",
        fiscal_period=fiscal_period,
        created_by="system",
    )
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=revenue_account,
        debit_credit="debit",
        amount=amount,
        description=f"Sales return / credit — {customer_name}",
    )
    JournalEntryLine.objects.create(
        journal_entry=journal_entry,
        account=ar_account,
        debit_credit="credit",
        amount=amount,
        description=f"AR reduction via credit {credit_invoice.invoice_number}",
    )
    _post_balanced_je(journal_entry, reference_type="credit_memo")
    payment.journal_entry = journal_entry
    payment.save(update_fields=["journal_entry"])
    return journal_entry


def create_customer_credit_memo(
    sales_order: SalesOrder,
    lines: list[dict[str, Any]],
    *,
    source_invoice: Invoice | None = None,
    restock: bool = True,
    notes: str = "",
    user=None,
) -> dict[str, Any]:
    """
    Process a customer return against a shipped SO.

    ``lines``: [{sales_order_item_id, quantity, unit_price?}, ...]
    """
    if not lines:
        raise SellFlowError("Add at least one return line.")

    so = SalesOrder.objects.select_related("customer").prefetch_related("items__item").get(
        pk=sales_order.pk
    )
    shipped_status = so.status in ("shipped", "completed") or any(
        float(i.quantity_shipped or 0) > 1e-6 for i in so.items.all()
    )
    if not shipped_status:
        raise SellFlowError(
            "Returns require shipped quantity. For wrong ship before payment, void invoice then Reverse shipment."
        )

    if source_invoice is None:
        source_invoice = (
            Invoice.objects.filter(sales_order=so, invoice_type="customer")
            .exclude(status="cancelled")
            .order_by("-invoice_date", "-id")
            .first()
        )
    if source_invoice and source_invoice.sales_order_id not in (None, so.id):
        raise SellFlowError("Source invoice is not for this sales order.")

    parsed: list[tuple[SalesOrderItem, float, float]] = []
    subtotal = 0.0
    for raw in lines:
        try:
            soi_id = int(raw.get("sales_order_item_id") or raw.get("line_id"))
            qty = float(raw.get("quantity") or 0)
        except (TypeError, ValueError) as e:
            raise SellFlowError("Invalid return line.") from e
        if qty <= 0:
            continue
        try:
            soi = SalesOrderItem.objects.select_related("item").get(
                pk=soi_id, sales_order=so
            )
        except SalesOrderItem.DoesNotExist as e:
            raise SellFlowError(f"Order line {soi_id} not found.") from e
        shipped = float(soi.quantity_shipped or 0)
        if qty > shipped + 1e-6:
            raise SellFlowError(
                f"Return qty {qty} exceeds shipped {shipped} for {soi.item.sku}."
            )
        unit_price = raw.get("unit_price")
        if unit_price is None or unit_price == "":
            unit_price = float(soi.unit_price or 0)
        else:
            unit_price = float(unit_price)
        if unit_price < 0:
            raise SellFlowError("Unit price cannot be negative.")
        line_total = round(qty * unit_price, 2)
        subtotal += line_total
        parsed.append((soi, qty, unit_price))

    if not parsed:
        raise SellFlowError("Enter a return quantity greater than 0.")
    subtotal = round(subtotal, 2)
    if subtotal <= 0:
        raise SellFlowError("Credit amount must be greater than zero.")

    from .views import generate_invoice_number, generate_lot_number

    today = timezone.localdate()
    actor = getattr(user, "username", None) or "system"
    unapplied = 0.0
    applied = 0.0
    restock_lots: list[Lot] = []
    payment = None

    with transaction.atomic():
        inv_notes = (
            f"CREDIT MEMO for SO {so.so_number}"
            + (f" / source invoice {source_invoice.invoice_number}" if source_invoice else "")
            + (f"\n{notes.strip()}" if notes and notes.strip() else "")
            + f"\nCreated by {actor}"
        )
        credit = Invoice.objects.create(
            invoice_number=generate_invoice_number(),
            invoice_type="credit",
            customer_vendor_name=so.customer_name
            or (so.customer.name if so.customer_id else ""),
            sales_order=so,
            invoice_date=today,
            due_date=today,
            status="sent",
            subtotal=subtotal,
            freight=0.0,
            tax=0.0,
            tax_amount=0.0,
            discount=0.0,
            grand_total=subtotal,
            total_amount=subtotal,
            paid_amount=0.0,
            notes=inv_notes,
        )
        for soi, qty, unit_price in parsed:
            InvoiceItem.objects.create(
                invoice=credit,
                item=soi.item,
                sales_order_item=soi,
                description=f"Return credit — {soi.item.sku} {soi.item.name}",
                quantity=qty,
                unit_price=unit_price,
                total=round(qty * unit_price, 2),
                notes="customer return",
            )

        if restock:
            for soi, qty, _unit_price in parsed:
                lot = Lot.objects.create(
                    lot_number=generate_lot_number(),
                    item=soi.item,
                    quantity=qty,
                    quantity_remaining=qty,
                    received_date=timezone.now(),
                    status="accepted",
                    short_reason=f"Customer return {so.so_number} / {credit.invoice_number}"[:255],
                )
                InventoryTransaction.objects.create(
                    transaction_type="receipt",
                    lot=lot,
                    quantity=qty,
                    reference_number=credit.invoice_number,
                    notes=f"Restock from customer return ({so.so_number})",
                )
                restock_lots.append(lot)

        ar = None
        if source_invoice:
            ar = (
                AccountsReceivable.objects.filter(invoice=source_invoice)
                .exclude(status="cancelled")
                .order_by("id")
                .first()
            )
        if ar and float(ar.balance or 0) > 0.01:
            apply_amt = min(subtotal, float(ar.balance or 0))
            apply_amt = round(apply_amt, 2)
            payment = Payment.objects.create(
                payment_type="ar_payment",
                payment_date=today,
                payment_method="other",
                amount=apply_amt,
                reference_number=credit.invoice_number,
                ar_entry=ar,
                notes=f"Applied credit memo {credit.invoice_number}",
            )
            ar.amount_paid = float(ar.amount_paid or 0) + apply_amt
            ar.balance = max(0.0, float(ar.original_amount or 0) - ar.amount_paid)
            if ar.balance <= 0.01:
                ar.balance = 0.0
                ar.status = "paid"
                if source_invoice.status not in ("paid", "cancelled"):
                    source_invoice.status = "paid"
                    source_invoice.paid_amount = float(source_invoice.grand_total or 0)
                    source_invoice.save(update_fields=["status", "paid_amount", "updated_at"])
            elif ar.amount_paid > 0:
                ar.status = "partial"
            ar.save()
            _create_credit_application_je(
                amount=apply_amt,
                customer_name=ar.customer_name,
                credit_invoice=credit,
                ar_entry=ar,
                payment=payment,
            )
            applied = apply_amt
            unapplied = round(subtotal - apply_amt, 2)
        else:
            unapplied = subtotal

        if unapplied > 0.01:
            note = (credit.notes or "").strip()
            bump = (
                f"Unapplied customer credit ${unapplied:,.2f} — "
                "apply on a future invoice or refund after bank confirmation (Mark paid / manual)."
            )
            credit.notes = f"{note}\n{bump}".strip() if note else bump
            credit.save(update_fields=["notes", "updated_at"])

    return {
        "credit_invoice": credit,
        "applied_amount": applied,
        "unapplied_amount": unapplied,
        "restock_lots": restock_lots,
        "payment": payment,
        "source_invoice": source_invoice,
    }
