"""
Customer RMA: open with credit (no restock), then dock check-in into -R staging lots on hold.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    CustomerRma,
    CustomerRmaLine,
    Lot,
    LotTransactionLog,
    SalesOrder,
    SalesOrderItem,
)
from .return_services import create_customer_credit_memo
from .sell_services import SellFlowError


def shipped_lot_quantities_for_so(sales_order: SalesOrder) -> list[dict[str, Any]]:
    """
    Lots depleted on this SO (picked up), with net shipped qty and remaining RMA capacity.
    Returns [{lot, sales_order_item, shipped_qty, already_rma_qty, available_qty}, ...]
    """
    so = sales_order
    # Sale logs store negative quantity_change; use abs for shipped.
    rows = (
        LotTransactionLog.objects.filter(
            sales_order_id=so.id,
            transaction_type="sale",
            lot_id__isnull=False,
        )
        .values("lot_id")
        .annotate(chg=Sum("quantity_change"))
    )
    lot_shipped: dict[int, float] = {}
    for row in rows:
        lid = row["lot_id"]
        shipped = abs(float(row["chg"] or 0))
        if shipped > 1e-6:
            lot_shipped[int(lid)] = lot_shipped.get(int(lid), 0.0) + shipped

    # Map lot → SO line via allocations (still present after ship) or item match.
    lot_ids = list(lot_shipped.keys())
    lots = {
        l.id: l
        for l in Lot.objects.filter(id__in=lot_ids).select_related("item", "pack_size")
    }
    from .models import SalesOrderLot

    alloc_map: dict[int, SalesOrderItem] = {}
    for sol in SalesOrderLot.objects.filter(
        sales_order_item__sales_order=so, lot_id__in=lot_ids
    ).select_related("sales_order_item__item"):
        alloc_map[sol.lot_id] = sol.sales_order_item

    # Fallback: match by item on SO lines
    items_by_sku = {
        i.item_id: i for i in SalesOrderItem.objects.filter(sales_order=so).select_related("item")
    }

    already = {}
    for line in CustomerRmaLine.objects.filter(
        rma__sales_order=so
    ).exclude(rma__status="cancelled"):
        key = (line.source_lot_id, line.sales_order_item_id)
        already[key] = already.get(key, 0.0) + float(line.quantity_requested or 0)

    out = []
    for lid, shipped in lot_shipped.items():
        lot = lots.get(lid)
        if lot is None:
            continue
        soi = alloc_map.get(lid)
        if soi is None:
            soi = items_by_sku.get(lot.item_id)
        if soi is None:
            continue
        rma_qty = already.get((lid, soi.id), 0.0)
        available = max(0.0, shipped - rma_qty)
        out.append(
            {
                "lot": lot,
                "sales_order_item": soi,
                "shipped_qty": shipped,
                "already_rma_qty": rma_qty,
                "available_qty": available,
            }
        )
    out.sort(key=lambda r: (r["sales_order_item"].item.sku, r["lot"].lot_number or ""))
    return out


def open_customer_rma(
    sales_order: SalesOrder,
    lines: list[dict[str, Any]],
    *,
    source_invoice=None,
    reason: str = "",
    notes: str = "",
    user=None,
) -> dict[str, Any]:
    """
    Open an RMA for a shipped SO and issue a credit memo (no inventory restock).

    ``lines``: [{sales_order_item_id, lot_id, quantity, unit_price?}, ...]
    """
    if not lines:
        raise SellFlowError("Select at least one lot / quantity to return.")

    so = SalesOrder.objects.select_related("customer").prefetch_related("items__item").get(
        pk=sales_order.pk
    )
    capacity = {
        (r["sales_order_item"].id, r["lot"].id): r
        for r in shipped_lot_quantities_for_so(so)
    }

    parsed: list[tuple[SalesOrderItem, Lot, float, float]] = []
    credit_lines: list[dict[str, Any]] = []
    # Aggregate credit by SOI for the memo (multiple lots on same line)
    by_soi: dict[int, dict[str, Any]] = {}

    for raw in lines:
        try:
            soi_id = int(raw.get("sales_order_item_id") or raw.get("line_id"))
            lot_id = int(raw.get("lot_id"))
            qty = float(raw.get("quantity") or 0)
        except (TypeError, ValueError) as e:
            raise SellFlowError("Invalid RMA line.") from e
        if qty <= 0:
            continue
        cap = capacity.get((soi_id, lot_id))
        if cap is None:
            raise SellFlowError(
                f"Lot {lot_id} was not shipped on this order (or is already fully on RMA)."
            )
        if qty > float(cap["available_qty"]) + 1e-6:
            raise SellFlowError(
                f"Return qty {qty} exceeds available {cap['available_qty']:.2f} "
                f"for lot {cap['lot'].lot_number}."
            )
        soi = cap["sales_order_item"]
        lot = cap["lot"]
        unit_price = raw.get("unit_price")
        if unit_price is None or unit_price == "":
            unit_price = float(soi.unit_price or 0)
        else:
            unit_price = float(unit_price)
        if unit_price < 0:
            raise SellFlowError("Unit price cannot be negative.")
        parsed.append((soi, lot, qty, unit_price))
        bucket = by_soi.setdefault(
            soi.id,
            {"sales_order_item_id": soi.id, "quantity": 0.0, "unit_price": unit_price},
        )
        bucket["quantity"] = float(bucket["quantity"]) + qty

    if not parsed:
        raise SellFlowError("Enter a return quantity greater than 0.")

    credit_lines = list(by_soi.values())
    actor = getattr(user, "username", None) or "system"

    from .views import generate_rma_number

    with transaction.atomic():
        credit_result = create_customer_credit_memo(
            so,
            credit_lines,
            source_invoice=source_invoice,
            restock=False,
            notes=(
                f"RMA credit\n{(reason or '').strip()}\n{(notes or '').strip()}"
            ).strip(),
            user=user,
        )
        credit = credit_result["credit_invoice"]
        rma = CustomerRma.objects.create(
            rma_number=generate_rma_number(),
            sales_order=so,
            customer_id=so.customer_id,
            status="open",
            credit_invoice=credit,
            reason=(reason or "").strip(),
            notes=(notes or "").strip(),
            opened_by=actor,
        )
        # Tag credit with RMA #
        inv_notes = (credit.notes or "").strip()
        credit.notes = f"{inv_notes}\nRMA {rma.rma_number}".strip()
        credit.save(update_fields=["notes", "updated_at"])

        rma_lines = []
        for soi, lot, qty, unit_price in parsed:
            rma_lines.append(
                CustomerRmaLine.objects.create(
                    rma=rma,
                    sales_order_item=soi,
                    source_lot=lot,
                    quantity_requested=qty,
                    quantity_received=0.0,
                    unit_price=unit_price,
                )
            )

    return {
        "rma": rma,
        "lines": rma_lines,
        "credit_invoice": credit,
        "applied_amount": credit_result["applied_amount"],
        "unapplied_amount": credit_result["unapplied_amount"],
    }


def refresh_rma_receive_status(rma: CustomerRma) -> CustomerRma:
    """Update RMA status from line receive totals."""
    if rma.status in ("cancelled", "closed"):
        return rma
    lines = list(rma.lines.all())
    if not lines:
        return rma
    total_req = sum(float(l.quantity_requested or 0) for l in lines)
    total_rec = sum(float(l.quantity_received or 0) for l in lines)
    if total_rec <= 1e-6:
        new_status = "open"
    elif total_rec + 1e-6 >= total_req:
        new_status = "received"
    else:
        new_status = "partially_received"
    if new_status != rma.status:
        rma.status = new_status
        rma.save(update_fields=["status", "updated_at"])
    return rma


def merge_rma_staging_into_source(
    staging_lot: Lot,
    *,
    qty: float,
    user=None,
    notes: str = "",
) -> Lot:
    """
    Move accepted qty from an RMA staging (-R) lot onto its source_lot, then
    clear that qty from the staging lot (retire when empty).
    """
    from .models import InventoryTransaction
    from .views import log_lot_transaction

    qty = round(float(qty), 2)
    if qty <= 0:
        raise SellFlowError("Merge quantity must be positive.")
    source = staging_lot.source_lot
    if source is None:
        raise SellFlowError(
            f"Staging lot {staging_lot.lot_number} has no source lot to merge into."
        )
    rem = float(staging_lot.quantity_remaining or 0)
    hold = float(staging_lot.quantity_on_hold or 0)
    if qty > rem + 1e-6:
        raise SellFlowError(f"Only {rem} remaining on staging lot.")
    if qty > hold + 1e-6:
        raise SellFlowError(f"Only {hold} on hold on staging lot.")

    actor = getattr(user, "username", None) or "system"
    with transaction.atomic():
        st_before = rem
        staging_lot.quantity_remaining = round(rem - qty, 2)
        staging_lot.quantity_on_hold = max(0.0, round(hold - qty, 2))
        if staging_lot.quantity_on_hold <= 1e-6:
            staging_lot.quantity_on_hold = 0.0
            staging_lot.on_hold = False
            staging_lot.status = "accepted"
        staging_lot.save()
        out_txn = InventoryTransaction.objects.create(
            transaction_type="adjustment",
            lot=staging_lot,
            quantity=-qty,
            reference_number=staging_lot.rma_number or "",
            notes=f"RMA accept merge out → {source.lot_number}"
            + (f": {notes}" if notes else ""),
        )
        log_lot_transaction(
            lot=staging_lot,
            quantity_before=st_before,
            quantity_change=-qty,
            transaction_type="adjustment",
            reference_number=staging_lot.rma_number or "",
            reference_type="rma_merge",
            transaction_id=out_txn.id,
            notes=f"Merged to {source.lot_number} by {actor}",
        )

        src_before = float(source.quantity_remaining or 0)
        source.quantity = float(source.quantity or 0) + qty
        source.quantity_remaining = round(src_before + qty, 2)
        if (source.status or "") == "on_hold" and float(source.quantity_on_hold or 0) <= 1e-6:
            source.status = "accepted"
            source.on_hold = False
        source.save()
        in_txn = InventoryTransaction.objects.create(
            transaction_type="return",
            lot=source,
            quantity=qty,
            reference_number=staging_lot.rma_number or "",
            notes=f"RMA accept merge in from {staging_lot.lot_number}"
            + (f": {notes}" if notes else ""),
        )
        log_lot_transaction(
            lot=source,
            quantity_before=src_before,
            quantity_change=qty,
            transaction_type="return",
            reference_number=staging_lot.rma_number or "",
            reference_type="rma_merge",
            transaction_id=in_txn.id,
            notes=f"Merged from {staging_lot.lot_number} by {actor}",
        )
    source.refresh_from_db()
    return source
