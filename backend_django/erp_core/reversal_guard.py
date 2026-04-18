"""
Central preconditions for reversing production/repack batches and related unwind ordering.

Batch reverse must not run while lots from the batch are still committed to active sales
allocations or to shipped inventory (Shipment). Reversing a shipment first restores
inventory and draft invoices via erp_core.shipment_reversal.reverse_shipment.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

SHIPMENT_ID_IN_NOTES = re.compile(r"Shipment\s+(\d+)", re.IGNORECASE)

# Inventory transactions created at ship-out (see SalesOrderViewSet.ship).
SHIP_TXN_MARKER = "Shipped for sales order"


def _shipment_ids_from_lot_ship_transactions(lot_ids: List[int]) -> Dict[int, Set[int]]:
    """Map lot_id -> set of shipment ids implied by inventory transaction notes."""
    from .models import InventoryTransaction

    if not lot_ids:
        return {}
    out: Dict[int, Set[int]] = {lid: set() for lid in lot_ids}
    qs = InventoryTransaction.objects.filter(lot_id__in=lot_ids).only("lot_id", "notes")
    for txn in qs.iterator():
        notes = txn.notes or ""
        if SHIP_TXN_MARKER not in notes:
            continue
        m = SHIPMENT_ID_IN_NOTES.search(notes)
        if not m:
            continue
        sid = int(m.group(1))
        lid = txn.lot_id
        if lid in out:
            out[lid].add(sid)
    return out


def get_production_batch_reversal_blockers(batch) -> List[Dict[str, Any]]:
    """
    Return a list of blocker dicts if batch.reverse() must not run yet.
    Empty list means reverse is allowed (subject to DB constraints).
    """
    from .models import Lot, SalesOrderLot, Shipment

    blockers: List[Dict[str, Any]] = []

    output_lot_ids = [int(x) for x in batch.outputs.values_list("lot_id", flat=True) if x]
    input_lot_ids = [int(x) for x in batch.inputs.values_list("lot_id", flat=True) if x]
    all_lot_ids = list({*output_lot_ids, *input_lot_ids})

    lot_by_id = {lot.pk: lot for lot in Lot.objects.filter(pk__in=all_lot_ids).only("id", "lot_number")}

    # 1) Active sales allocations (not yet shipped / still committed)
    sol_qs = (
        SalesOrderLot.objects.filter(lot_id__in=all_lot_ids, quantity_allocated__gt=0)
        .select_related("sales_order_item__sales_order", "lot")
        .order_by("id")
    )
    for sol in sol_qs:
        so = sol.sales_order_item.sales_order
        lot = sol.lot
        blockers.append(
            {
                "code": "ACTIVE_SALES_ALLOCATION",
                "message": (
                    f'Lot {(lot.lot_number or str(lot.pk))} has {sol.quantity_allocated:g} units '
                    f'allocated to sales order {so.so_number}. Remove or reduce allocations before reversing this batch.'
                ),
                "sales_order_lot_id": sol.pk,
                "sales_order_id": so.pk,
                "so_number": so.so_number,
                "lot_id": lot.pk,
                "lot_number": lot.lot_number,
                "quantity_allocated": float(sol.quantity_allocated or 0),
            }
        )

    # 2) Shipments not yet reversed (inventory still shows ship-out txns)
    ship_map = _shipment_ids_from_lot_ship_transactions(all_lot_ids)
    seen_shipments: Set[int] = set()
    for lot_id, sids in ship_map.items():
        for sid in sids:
            if sid in seen_shipments:
                continue
            seen_shipments.add(sid)
            try:
                sh = Shipment.objects.select_related("sales_order").get(pk=sid)
                so = sh.sales_order
                lot_number = ""
                if lot_id in lot_by_id:
                    lot_number = lot_by_id[lot_id].lot_number or str(lot_id)
                blockers.append(
                    {
                        "code": "ACTIVE_SHIPMENT",
                        "message": (
                            f'Lot {lot_number or lot_id} has inventory shipped on shipment #{sid} '
                            f'(SO {so.so_number}). Reverse that shipment first (restores stock and removes draft invoices tied to it).'
                        ),
                        "shipment_id": sid,
                        "sales_order_id": so.pk,
                        "so_number": so.so_number,
                        "lot_id": lot_id,
                    }
                )
            except Shipment.DoesNotExist:
                # Stale note referencing deleted shipment — still block with generic message
                blockers.append(
                    {
                        "code": "SHIPMENT_LEDGER_ORPHAN",
                        "message": (
                            f"Lot {lot_id} has shipment-related inventory lines (shipment id {sid} not found). "
                            "Resolve inventory history before reversing this batch."
                        ),
                        "shipment_id": sid,
                        "lot_id": lot_id,
                    }
                )

    # One row per shipment id for ACTIVE_SHIPMENT (multiple lots may share a release)
    merged: List[Dict[str, Any]] = []
    shipment_seen: Set[int] = set()
    for b in blockers:
        if b.get("code") == "ACTIVE_SHIPMENT" and b.get("shipment_id"):
            sid = int(b["shipment_id"])
            if sid in shipment_seen:
                continue
            shipment_seen.add(sid)
        merged.append(b)
    return merged


def build_batch_reversal_plan(batch) -> Dict[str, Any]:
    """
    Machine-readable unwind plan: blockers + suggested step order (shipments first, then batch).
    """
    blockers = get_production_batch_reversal_blockers(batch)
    shipment_steps: List[Dict[str, Any]] = []
    shipment_ids: Set[int] = set()
    for b in blockers:
        if b.get("code") == "ACTIVE_SHIPMENT" and b.get("shipment_id"):
            sid = int(b["shipment_id"])
            if sid not in shipment_ids:
                shipment_ids.add(sid)
                shipment_steps.append(
                    {
                        "order": len(shipment_steps) + 1,
                        "action": "reverse_shipment",
                        "method": "POST",
                        "path": f"/api/shipments/{sid}/reverse/",
                        "shipment_id": sid,
                        "description": b.get("message", ""),
                    }
                )

    alloc_steps: List[Dict[str, Any]] = []
    for b in blockers:
        if b.get("code") == "ACTIVE_SALES_ALLOCATION":
            alloc_steps.append(
                {
                    "order": len(alloc_steps) + 1,
                    "action": "clear_sales_allocation",
                    "sales_order_lot_id": b.get("sales_order_lot_id"),
                    "sales_order_id": b.get("sales_order_id"),
                    "so_number": b.get("so_number"),
                    "description": b.get("message", ""),
                }
            )

    next_order = 1
    steps: List[Dict[str, Any]] = []
    for s in shipment_steps:
        steps.append({**s, "order": next_order})
        next_order += 1
    for s in alloc_steps:
        steps.append({**s, "order": next_order})
        next_order += 1

    batch_id = batch.pk
    steps.append(
        {
            "order": next_order,
            "action": "reverse_production_batch",
            "method": "POST",
            "path": f"/api/production-batches/{batch_id}/reverse/",
            "batch_id": batch_id,
            "batch_number": getattr(batch, "batch_number", None),
            "description": "Reverse the batch ticket (after steps above are complete).",
        }
    )

    can_reverse_now = len(blockers) == 0
    return {
        "target": {
            "type": "production_batch",
            "id": batch.pk,
            "batch_number": getattr(batch, "batch_number", None),
            "status": getattr(batch, "status", None),
        },
        "can_reverse_now": can_reverse_now,
        "blockers": blockers,
        "suggested_steps": steps if not can_reverse_now else steps[-1:],
    }
