"""Lot mass-balance / full traceability for Quality lot tracking."""
from __future__ import annotations

from django.db.models import Q

from django.utils import timezone

from .models import (
    CustomerRmaLine,
    InventoryTransaction,
    Lot,
    LotTransactionLog,
    ProductionBatchInput,
    ProductionBatchOutput,
    SalesOrderLot,
)


def resolve_lots_for_search(term: str) -> list[Lot]:
    term = (term or "").strip()
    if not term:
        return []
    return list(
        Lot.objects.select_related("item", "source_lot")
        .filter(Q(lot_number__iexact=term) | Q(vendor_lot_number__iexact=term))
        .order_by("-received_date", "-id")[:25]
    )


def build_lot_mass_balance(lot: Lot) -> dict:
    """
    Full pedigree + ledger + green/red balance for one lot.

    Balance: sum(LTL quantity_change) + first_before ≈ remaining; also compare
    last quantity_after to Lot.quantity_remaining.
    """
    logs = list(
        LotTransactionLog.objects.filter(lot=lot).order_by("logged_at", "id")
    )
    # Backfill production_output from InventoryTransaction when LTL missing
    has_prod_out_ltl = any(l.transaction_type == "production_output" for l in logs)
    if not has_prod_out_ltl:
        for txn in InventoryTransaction.objects.filter(
            lot=lot, transaction_type="production_output"
        ).order_by("transaction_date"):
            logs.append(
                type(
                    "SynthLog",
                    (),
                    {
                        "id": 0,
                        "logged_at": txn.transaction_date,
                        "transaction_type": "production_output",
                        "quantity_change": float(txn.quantity or 0),
                        "quantity_before": None,
                        "quantity_after": None,
                        "reference_number": txn.reference_number,
                        "notes": txn.notes,
                        "po_number": None,
                        "is_synthetic": True,
                    },
                )()
            )

    by_type: dict[str, float] = {}
    for log in logs:
        t = log.transaction_type or "other"
        by_type[t] = by_type.get(t, 0.0) + float(log.quantity_change or 0)

    def _sum_types(*keys):
        return round(sum(by_type.get(k, 0.0) for k in keys), 4)

    brought_in = _sum_types("receipt", "production_output", "repack_output", "return")
    used_out = abs(
        _sum_types(
            "production_input",
            "repack_input",
            "sale",
            "lab_stock",
            "indirect_material_consumption",
            "indirect_material_checkout",
        )
    )
    adjustments = _sum_types("adjustment", "manual", "reversal")
    net_change = round(sum(float(l.quantity_change or 0) for l in logs), 4)

    remaining = float(lot.quantity_remaining or 0)
    # Reconstruct expected remaining from ledger when we have a starting point
    first_before = None
    last_after = None
    real_logs = [l for l in logs if getattr(l, "quantity_after", None) is not None]
    if real_logs:
        first_before = float(real_logs[0].quantity_before or 0)
        last_after = float(real_logs[-1].quantity_after or 0)
        expected = round(first_before + net_change, 4)
    else:
        expected = remaining
        last_after = remaining

    drift = round(remaining - (last_after if last_after is not None else remaining), 4)
    # Prefer last_after vs book remaining for green/red
    balanced = abs(drift) <= 0.05

    # Sections
    production_uses = []
    for inp in (
        ProductionBatchInput.objects.select_related("batch__finished_good_item")
        .filter(lot=lot)
        .order_by("-batch__production_date")[:50]
    ):
        production_uses.append(
            {
                "batch_number": inp.batch.batch_number,
                "finished_good": inp.batch.finished_good_item.name,
                "sku": inp.batch.finished_good_item.sku,
                "quantity_used": inp.quantity_used,
                "date": inp.batch.production_date,
                "batch_type": inp.batch.batch_type,
            }
        )

    produced_from = []
    for out in (
        ProductionBatchOutput.objects.select_related("batch")
        .filter(lot=lot)
        .order_by("-batch__production_date")[:20]
    ):
        inputs = list(
            ProductionBatchInput.objects.select_related("lot__item")
            .filter(batch=out.batch)
            .order_by("id")
        )
        produced_from.append(
            {
                "batch_number": out.batch.batch_number,
                "quantity_produced": out.quantity_produced,
                "date": out.batch.production_date,
                "batch_type": out.batch.batch_type,
                "inputs": inputs,
            }
        )

    sales_rows = []
    for log in logs:
        if log.transaction_type != "sale":
            continue
        sales_rows.append(
            {
                "qty": abs(float(log.quantity_change or 0)),
                "so": log.reference_number,
                "sales_order_id": getattr(log, "sales_order_id", None),
                "date": log.logged_at,
                "notes": log.notes,
            }
        )
    open_allocs = list(
        SalesOrderLot.objects.filter(lot=lot, quantity_allocated__gt=0)
        .select_related("sales_order_item__sales_order")
        .order_by("-id")[:30]
    )

    po_rows = [
        {
            "qty": float(log.quantity_change or 0),
            "po": log.reference_number or log.po_number,
            "date": log.logged_at,
        }
        for log in logs
        if log.transaction_type == "receipt"
    ]

    return_rows = [
        {
            "qty": float(log.quantity_change or 0),
            "ref": log.reference_number,
            "date": log.logged_at,
            "notes": log.notes,
        }
        for log in logs
        if log.transaction_type == "return"
    ]
    rma_staging = list(
        Lot.objects.filter(source_lot=lot).select_related("item").order_by("-id")[:20]
    )
    rma_as_staging = list(
        CustomerRmaLine.objects.filter(staging_lot=lot)
        .select_related("rma", "source_lot")
        .order_by("-id")[:10]
    )

    lab_rows = [
        {
            "qty": abs(float(log.quantity_change or 0)),
            "date": log.logged_at,
            "notes": log.notes,
        }
        for log in logs
        if log.transaction_type == "lab_stock"
    ]

    ledger = []
    for log in sorted(
        logs,
        key=lambda x: (
            x.logged_at or timezone.now().replace(year=1970, month=1, day=1),
            getattr(x, "id", 0) or 0,
        ),
    ):
        ledger.append(
            {
                "date": log.logged_at,
                "type": log.transaction_type,
                "type_display": (
                    log.get_transaction_type_display()
                    if callable(getattr(log, "get_transaction_type_display", None))
                    else (log.transaction_type or "").replace("_", " ").title()
                ),
                "change": float(log.quantity_change or 0),
                "after": getattr(log, "quantity_after", None),
                "ref": getattr(log, "reference_number", None),
                "notes": getattr(log, "notes", None),
                "synthetic": getattr(log, "is_synthetic", False),
            }
        )

    return {
        "lot": lot,
        "remaining": remaining,
        "original_qty": float(lot.quantity or 0),
        "brought_in": brought_in,
        "used_out": used_out,
        "adjustments": adjustments,
        "net_change": net_change,
        "ledger_after": last_after,
        "expected_remaining": expected,
        "drift": drift,
        "balanced": balanced,
        "production_uses": production_uses,
        "produced_from": produced_from,
        "sales_rows": sales_rows,
        "open_allocs": open_allocs,
        "po_rows": po_rows,
        "return_rows": return_rows,
        "rma_staging": rma_staging,
        "rma_as_staging": rma_as_staging,
        "lab_rows": lab_rows,
        "ledger": ledger,
        "po_number": lot.po_number,
        "rma_number": getattr(lot, "rma_number", None),
    }
