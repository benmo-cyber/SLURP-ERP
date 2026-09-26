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
    SalesOrder,
    SalesOrderLot,
    Vendor,
)


def resolve_lots_for_search(term: str) -> list[Lot]:
    """
    Resolve lots for Quality lot tracking.

    Prefer exact WWI / vendor lot #, then substring matches, then digit-prefix
    suggestions (e.g. ``1260017`` → nearby ``126001xx`` lots when nothing exact).
    """
    term = (term or "").strip()
    if not term:
        return []
    qs = Lot.objects.select_related("item", "source_lot")
    exact = list(
        qs.filter(Q(lot_number__iexact=term) | Q(vendor_lot_number__iexact=term))
        .order_by("-received_date", "-id")[:25]
    )
    if exact:
        return exact

    partial = list(
        qs.filter(Q(lot_number__icontains=term) | Q(vendor_lot_number__icontains=term))
        .order_by("-received_date", "-id")[:25]
    )
    if partial:
        return partial

    # Truncated / mistyped internal lot # — suggest same prefix family.
    digits = "".join(ch for ch in term if ch.isdigit())
    if len(digits) >= 5:
        prefix = digits[:6] if len(digits) >= 6 else digits
        return list(qs.filter(lot_number__startswith=prefix).order_by("lot_number", "id")[:25])
    return []


def _is_sale_txn(transaction_type: str | None) -> bool:
    """Pickup writes both ``sale`` (LTL) and ``sales`` (depletion) — treat as one."""
    return (transaction_type or "") in ("sale", "sales")


def _sale_dedupe_key(lot_id, reference_number, quantity_change) -> tuple:
    return (
        lot_id,
        (reference_number or "").strip(),
        round(abs(float(quantity_change or 0)), 4),
    )


def _lot_uom(lot: Lot | None) -> str:
    if not lot:
        return ""
    item = getattr(lot, "item", None)
    return (getattr(item, "unit_of_measure", None) or "").strip()


def _so_customer_ship_labels(so: SalesOrder | None) -> tuple[str, str]:
    """Return (customer_name, ship_to_label) for display next to an SO #."""
    if so is None:
        return "", ""
    customer = ""
    if getattr(so, "customer_id", None) and getattr(so, "customer", None):
        customer = (so.customer.name or "").strip()
    if not customer:
        customer = (so.customer_name or "").strip()

    ship_to = ""
    loc = getattr(so, "ship_to_location", None)
    if loc is not None:
        ship_to = (loc.location_name or "").strip()
        if not ship_to:
            parts = [
                (loc.city or "").strip(),
                (loc.state or "").strip(),
            ]
            ship_to = ", ".join(p for p in parts if p)
    if not ship_to:
        # Legacy SO fields
        parts = [
            (so.customer_city or "").strip(),
            (so.customer_state or "").strip(),
        ]
        ship_to = ", ".join(p for p in parts if p)
    return customer, ship_to


def _sales_order_lookup_map(
    *,
    so_ids: list[int] | None = None,
    so_numbers: list[str] | None = None,
) -> dict:
    """Map sales_order id and so_number → SalesOrder (with customer / ship-to)."""
    qs = SalesOrder.objects.select_related("customer", "ship_to_location")
    by_id: dict[int, SalesOrder] = {}
    by_num: dict[str, SalesOrder] = {}
    ids = [int(x) for x in (so_ids or []) if x]
    nums = [str(x).strip() for x in (so_numbers or []) if (x or "").strip()]
    if ids:
        for so in qs.filter(id__in=ids):
            by_id[so.id] = so
            if so.so_number:
                by_num[so.so_number.strip()] = so
    missing_nums = [n for n in nums if n not in by_num]
    if missing_nums:
        for so in qs.filter(so_number__in=missing_nums):
            by_id[so.id] = so
            if so.so_number:
                by_num[so.so_number.strip()] = so
    return {"by_id": by_id, "by_num": by_num}


def _attach_so_party(row: dict, lookup: dict) -> None:
    so = None
    sid = row.get("sales_order_id")
    if sid:
        so = lookup["by_id"].get(int(sid))
    if so is None:
        num = (row.get("so") or row.get("so_number") or "").strip()
        if num:
            so = lookup["by_num"].get(num)
    customer, ship_to = _so_customer_ship_labels(so)
    row["customer"] = customer
    row["ship_to"] = ship_to
    if so is not None and not row.get("sales_order_id"):
        row["sales_order_id"] = so.id


def _forward_output_lots(seed_lot_ids: list[int], *, max_depth: int = 4, max_lots: int = 120):
    """
    Walk seed lots → batches that consume them → output lots, recursively.

    Covers RM → FG sold, and RM → FG → rework/repack → FG sold.
    Returns (output_rows, lot_id → batch, lot_id → qty of seed lot used on path).
    """
    frontier = {int(x) for x in seed_lot_ids if x}
    seen_lots = set(frontier)
    output_rows = []
    lot_to_batch: dict[int, object] = {}
    # Seed lots themselves: no "used" attribution yet
    lot_to_seed_used: dict[int, float | None] = {lid: None for lid in frontier}
    seed_ids = set(frontier)

    for _ in range(max_depth):
        if not frontier or len(output_rows) >= max_lots:
            break
        inputs = list(
            ProductionBatchInput.objects.filter(lot_id__in=frontier).order_by("id")
        )
        if not inputs:
            break

        seed_used_in_batch: dict[int, float] = {}
        inherited_seed_in_batch: dict[int, float] = {}
        batch_ids: list[int] = []
        for inp in inputs:
            if inp.batch_id not in batch_ids:
                batch_ids.append(inp.batch_id)
            qty = float(inp.quantity_used or 0)
            if inp.lot_id in seed_ids:
                seed_used_in_batch[inp.batch_id] = (
                    seed_used_in_batch.get(inp.batch_id, 0.0) + qty
                )
            else:
                parent_used = lot_to_seed_used.get(inp.lot_id)
                if parent_used is not None and inp.batch_id not in seed_used_in_batch:
                    inherited_seed_in_batch[inp.batch_id] = (
                        inherited_seed_in_batch.get(inp.batch_id, 0.0) + parent_used
                    )

        outs = list(
            ProductionBatchOutput.objects.filter(batch_id__in=batch_ids)
            .select_related("lot__item", "batch")
            .order_by("-batch__production_date", "id")[:max_lots]
        )
        next_frontier = set()
        for out in outs:
            if not out.lot_id or out.lot_id in seen_lots:
                continue
            seen_lots.add(out.lot_id)
            next_frontier.add(out.lot_id)
            output_rows.append(out)
            if out.batch_id:
                lot_to_batch[out.lot_id] = out.batch
            if out.batch_id in seed_used_in_batch:
                lot_to_seed_used[out.lot_id] = seed_used_in_batch[out.batch_id]
            elif out.batch_id in inherited_seed_in_batch:
                lot_to_seed_used[out.lot_id] = inherited_seed_in_batch[out.batch_id]
            else:
                lot_to_seed_used[out.lot_id] = None
            if len(output_rows) >= max_lots:
                break
        frontier = next_frontier

    return output_rows, lot_to_batch, lot_to_seed_used


def build_lot_mass_balance(lot: Lot) -> dict:
    """
    Full pedigree + ledger + green/red balance for one lot.

    Balance: sum(LTL quantity_change) + first_before ≈ remaining; also compare
    last quantity_after to Lot.quantity_remaining.
    """
    logs = list(
        LotTransactionLog.objects.filter(lot=lot).order_by("logged_at", "id")
    )
    lot_uom = _lot_uom(lot)
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
    sale_seen_for_balance: set[tuple] = set()
    sale_qty_once = 0.0
    for log in logs:
        t = log.transaction_type or "other"
        if _is_sale_txn(t):
            key = _sale_dedupe_key(lot.id, log.reference_number, log.quantity_change)
            if key in sale_seen_for_balance:
                continue
            sale_seen_for_balance.add(key)
            sale_qty_once += float(log.quantity_change or 0)
            continue
        by_type[t] = by_type.get(t, 0.0) + float(log.quantity_change or 0)

    def _sum_types(*keys):
        return round(sum(by_type.get(k, 0.0) for k in keys), 4)

    brought_in = _sum_types("receipt", "production_output", "repack_output", "return")
    used_out = abs(
        _sum_types(
            "production_input",
            "repack_input",
            "lab_stock",
            "indirect_material_consumption",
            "indirect_material_checkout",
        )
        + sale_qty_once
    )
    adjustments = _sum_types("adjustment", "manual", "reversal")
    # Net ledger change excluding duplicate sale/sales pairs
    net_change = round(
        sum(
            float(l.quantity_change or 0)
            for l in logs
            if not _is_sale_txn(l.transaction_type)
        )
        + sale_qty_once,
        4,
    )

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
    # Human-readable lot story (In + Adj − Out). Independent of ledger first_before math.
    story_expected = round(float(brought_in) + float(adjustments) - float(used_out), 4)

    # Sections — production uses (+ direct output lots on those batches)
    direct_output_lots = []
    out_by_batch: dict[int, list] = {}
    input_batch_ids = list(
        ProductionBatchInput.objects.filter(lot=lot)
        .values_list("batch_id", flat=True)
        .distinct()
    )
    if input_batch_ids:
        direct_output_lots = list(
            ProductionBatchOutput.objects.filter(batch_id__in=input_batch_ids)
            .select_related("lot__item", "batch")
            .order_by("-batch__production_date", "id")[:80]
        )
        for out in direct_output_lots:
            out_by_batch.setdefault(out.batch_id, []).append(out)

    production_uses = []
    for inp in (
        ProductionBatchInput.objects.select_related("batch__finished_good_item", "batch")
        .filter(lot=lot)
        .order_by("-batch__production_date")[:50]
    ):
        outs = out_by_batch.get(inp.batch_id) or []
        fg_item = getattr(inp.batch, "finished_good_item", None)
        production_uses.append(
            {
                "batch_number": inp.batch.batch_number,
                "batch_id": inp.batch_id,
                "finished_good": (fg_item.name if fg_item else "—"),
                "sku": (fg_item.sku if fg_item else ""),
                "quantity_used": inp.quantity_used,
                "date": inp.batch.production_date,
                "batch_type": inp.batch.batch_type,
                "output_lots": [
                    {
                        "lot_number": o.lot.lot_number if o.lot_id else "—",
                        "lot_id": o.lot_id,
                        "sku": (o.lot.item.sku if o.lot_id and o.lot.item_id else ""),
                        "qty": o.quantity_produced,
                    }
                    for o in outs
                    if o.lot_id
                ],
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
                "batch_id": out.batch_id,
                "quantity_produced": out.quantity_produced,
                "date": out.batch.production_date,
                "batch_type": out.batch.batch_type,
                "inputs": inputs,
            }
        )

    sales_rows = []
    seen_direct_sales: set[tuple] = set()
    for log in logs:
        if not _is_sale_txn(log.transaction_type):
            continue
        key = _sale_dedupe_key(lot.id, log.reference_number, log.quantity_change)
        if key in seen_direct_sales:
            continue
        seen_direct_sales.add(key)
        sales_rows.append(
            {
                "qty": abs(float(log.quantity_change or 0)),
                "uom": lot_uom or getattr(log, "unit_of_measure", None) or "",
                "so": log.reference_number,
                "sales_order_id": getattr(log, "sales_order_id", None),
                "date": log.logged_at,
                "notes": log.notes,
                "via": "direct",
            }
        )
    open_alloc_rows = []
    for sol in (
        SalesOrderLot.objects.filter(lot=lot, quantity_allocated__gt=0)
        .select_related(
            "sales_order_item__sales_order__customer",
            "sales_order_item__sales_order__ship_to_location",
            "lot__item",
        )
        .order_by("-id")[:30]
    ):
        so = sol.sales_order_item.sales_order
        open_alloc_rows.append(
            {
                "so_number": so.so_number,
                "sales_order_id": so.id,
                "qty": float(sol.quantity_allocated or 0),
                "uom": lot_uom or _lot_uom(sol.lot),
                "status": so.status,
            }
        )

    # Open production / rework / repack tickets that have staged this lot as an input
    # (draft / scheduled / in progress — not yet closed).
    production_alloc_rows = []
    for inp in (
        ProductionBatchInput.objects.filter(
            lot=lot,
            batch__status__in=("draft", "scheduled", "in_progress"),
        )
        .select_related("batch__finished_good_item", "batch")
        .order_by("-batch__production_date", "-id")[:50]
    ):
        fg = getattr(inp.batch, "finished_good_item", None)
        production_alloc_rows.append(
            {
                "batch_number": inp.batch.batch_number,
                "batch_id": inp.batch_id,
                "batch_type": inp.batch.batch_type,
                "status": inp.batch.status,
                "finished_good": (fg.name if fg else "—"),
                "sku": (fg.sku if fg else ""),
                "qty": float(inp.quantity_used or 0),
                "uom": lot_uom,
                "date": inp.batch.production_date,
            }
        )

    # Forward sales: FG/DI (and further rework/repack) from batches that consumed
    # this lot — RM → make → FG sold is not on this lot's own sale ledger.
    downstream_sales_rows = []
    downstream_open_allocs = []
    seen_sale_keys = set()
    seen_alloc_ids = set()
    forward_outs, lot_to_batch, lot_to_seed_used = _forward_output_lots([lot.id])
    fg_lot_ids = [o.lot_id for o in forward_outs if o.lot_id]
    if fg_lot_ids:
        for sol in (
            SalesOrderLot.objects.filter(lot_id__in=fg_lot_ids, quantity_allocated__gt=0)
            .select_related(
                "lot__item",
                "sales_order_item__sales_order__customer",
                "sales_order_item__sales_order__ship_to_location",
            )
            .order_by("-id")[:80]
        ):
            if sol.id in seen_alloc_ids:
                continue
            so = sol.sales_order_item.sales_order
            batch = lot_to_batch.get(sol.lot_id)
            seed_used = lot_to_seed_used.get(sol.lot_id)
            downstream_open_allocs.append(
                {
                    "so_number": so.so_number,
                    "sales_order_id": so.id,
                    "fg_lot": sol.lot.lot_number if sol.lot_id else "—",
                    "fg_sku": (
                        sol.lot.item.sku if sol.lot_id and sol.lot.item_id else ""
                    ),
                    "qty": float(sol.quantity_allocated or 0),
                    "uom": _lot_uom(sol.lot),
                    "this_lot_used": seed_used,
                    "this_lot_uom": lot_uom,
                    "batch_number": batch.batch_number if batch else "—",
                    "status": so.status,
                }
            )
            seen_alloc_ids.add(sol.id)

        for log in (
            LotTransactionLog.objects.filter(
                lot_id__in=fg_lot_ids,
                transaction_type__in=("sale", "sales"),
            )
            .select_related("lot__item")
            .order_by("-logged_at", "-id")[:160]
        ):
            key = _sale_dedupe_key(log.lot_id, log.reference_number, log.quantity_change)
            if key in seen_sale_keys:
                continue
            seen_sale_keys.add(key)
            batch = lot_to_batch.get(log.lot_id)
            seed_used = lot_to_seed_used.get(log.lot_id)
            downstream_sales_rows.append(
                {
                    "qty": abs(float(log.quantity_change or 0)),
                    "uom": _lot_uom(log.lot) or getattr(log, "unit_of_measure", None) or "",
                    "so": log.reference_number,
                    "sales_order_id": getattr(log, "sales_order_id", None),
                    "date": log.logged_at,
                    "notes": log.notes,
                    "via": "downstream",
                    "fg_lot": log.lot.lot_number if log.lot_id else "—",
                    "fg_sku": (
                        log.lot.item.sku if log.lot_id and log.lot.item_id else ""
                    ),
                    "batch_number": batch.batch_number if batch else "—",
                    "this_lot_used": seed_used,
                    "this_lot_uom": lot_uom,
                }
            )

    # Attach customer / ship-to for every SO-linked activity row.
    so_lookup = _sales_order_lookup_map(
        so_ids=[
            *(r.get("sales_order_id") for r in sales_rows),
            *(r.get("sales_order_id") for r in open_alloc_rows),
            *(r.get("sales_order_id") for r in downstream_sales_rows),
            *(r.get("sales_order_id") for r in downstream_open_allocs),
        ],
        so_numbers=[
            *(r.get("so") for r in sales_rows),
            *(r.get("so_number") for r in open_alloc_rows),
            *(r.get("so") for r in downstream_sales_rows),
            *(r.get("so_number") for r in downstream_open_allocs),
        ],
    )
    for row in (
        sales_rows
        + open_alloc_rows
        + downstream_sales_rows
        + downstream_open_allocs
    ):
        _attach_so_party(row, so_lookup)

    po_rows = [
        {
            "qty": float(log.quantity_change or 0),
            "uom": lot_uom or getattr(log, "unit_of_measure", None) or "",
            "po": log.reference_number or log.po_number,
            "date": log.logged_at,
        }
        for log in logs
        if log.transaction_type == "receipt"
    ]

    return_rows = [
        {
            "qty": float(log.quantity_change or 0),
            "uom": lot_uom or getattr(log, "unit_of_measure", None) or "",
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
            "uom": lot_uom or getattr(log, "unit_of_measure", None) or "",
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
                "uom": lot_uom or getattr(log, "unit_of_measure", None) or "",
                "ref": getattr(log, "reference_number", None),
                "notes": getattr(log, "notes", None),
                "synthetic": getattr(log, "is_synthetic", False),
            }
        )

    # Attach UoM onto production rows for template
    for row in production_uses:
        row["uom"] = lot_uom
        for ol in row.get("output_lots") or []:
            ol.setdefault("uom", "")  # FG uom filled below if we have it
    # Fill output lot UoMs from direct_output_lots
    out_uom_by_id = {
        o.lot_id: _lot_uom(o.lot) for o in direct_output_lots if o.lot_id
    }
    for row in production_uses:
        for ol in row.get("output_lots") or []:
            if ol.get("lot_id"):
                ol["uom"] = out_uom_by_id.get(ol["lot_id"], "")

    for batch in produced_from:
        batch["uom"] = lot_uom

    vendor_name = (getattr(getattr(lot, "item", None), "vendor", None) or "").strip() or None
    vendor_id = None
    if vendor_name:
        vendor_id = (
            Vendor.objects.filter(name__iexact=vendor_name)
            .values_list("id", flat=True)
            .first()
        )

    return {
        "lot": lot,
        "uom": lot_uom,
        "vendor_name": vendor_name,
        "vendor_id": vendor_id,
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
        "story_expected": story_expected,
        "production_uses": production_uses,
        "produced_from": produced_from,
        "sales_rows": sales_rows,
        "open_allocs": open_alloc_rows,
        "production_allocs": production_alloc_rows,
        "downstream_sales_rows": downstream_sales_rows,
        "downstream_open_allocs": downstream_open_allocs,
        "po_rows": po_rows,
        "return_rows": return_rows,
        "rma_staging": rma_staging,
        "rma_as_staging": rma_as_staging,
        "lab_rows": lab_rows,
        "ledger": ledger,
        "po_number": lot.po_number,
        "rma_number": getattr(lot, "rma_number", None),
    }
