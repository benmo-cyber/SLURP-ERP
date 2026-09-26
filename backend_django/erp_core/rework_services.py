"""
Rework: blend parent-family FG partials (optional strength adjust with RM lots)
into a new lot under a chosen pack SKU.

Create opens an in-progress ticket (allocates inputs; packaging consumed now).
Close consumes FG/RM inputs and creates the on-hold output awaiting micro.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from .formula_ingredient import parent_code_for_item, skus_for_parent_code
from .lot_display_quantities import compute_lot_quantity_breakdown
from .models import (
    InventoryTransaction,
    Item,
    Lot,
    ProductionBatch,
    ProductionBatchInput,
)
from .pack_display import lot_available_remnant_quantity


class ReworkError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def partial_lots_for_parent(parent_code: str) -> list[Lot]:
    """Accepted lots with free remnant under a parent family (Inventory Partials semantics)."""
    skus = skus_for_parent_code(parent_code)
    if not skus:
        return []
    lots = (
        Lot.objects.filter(
            item__sku__in=skus,
            item__item_type="finished_good",
            status="accepted",
            quantity_remaining__gt=0,
        )
        .select_related("item", "pack_size")
        .prefetch_related("item__pack_sizes")
        .order_by("-received_date")
    )
    out = []
    for lot in lots:
        work = lot_available_remnant_quantity(lot)
        if work > 1e-6:
            out.append(lot)
    return out


def execute_rework(
    *,
    target_item: Item,
    partial_lines: list[dict[str, Any]],
    adjust_lines: list[dict[str, Any]] | None = None,
    packaging_lines: list[dict[str, Any]] | None = None,
    notes: str = "",
    user=None,
) -> dict[str, Any]:
    """
    Open a rework ticket: allocate parent-family partials (+ optional RM adjust)
    under ``target_item``. Does not consume FG/RM or create output until Close.

    Packaging / indirect materials are consumed immediately (same as batch tickets).

    ``partial_lines``: [{lot_id, quantity?}] — quantity defaults to remnant available.
    ``adjust_lines``: [{lot_id, quantity}] — RM / other lots for strength adjust.
    ``packaging_lines``: [{lot_id, quantity_used}] — indirect packaging consumed now.
    """
    from .views import (
        _round_lot_qty_remaining,
        _round_production_quantity_used,
        generate_batch_number,
        log_lot_transaction,
    )

    if target_item is None or getattr(target_item, "item_type", "") not in (
        "finished_good",
        "distributed_item",
    ):
        raise ReworkError("Target must be a finished good or distributed item.")

    parent = parent_code_for_item(target_item)
    if not parent:
        raise ReworkError("Target item has no parent family code.")

    family_skus = set(skus_for_parent_code(parent))
    if (target_item.sku or "").strip() not in family_skus and not family_skus:
        family_skus.add((target_item.sku or "").strip())

    if not partial_lines:
        raise ReworkError("Select at least one parent-family partial to rework.")

    actor = getattr(user, "username", None) or "system"
    adjust_lines = adjust_lines or []
    packaging_lines = packaging_lines or []

    with transaction.atomic():
        allocated: list[tuple[Lot, float]] = []
        total = 0.0

        for raw in partial_lines:
            try:
                lid = int(raw.get("lot_id"))
            except (TypeError, ValueError) as e:
                raise ReworkError("Invalid partial lot.") from e
            try:
                lot = Lot.objects.select_related("item").get(pk=lid, status="accepted")
            except Lot.DoesNotExist as e:
                raise ReworkError(f"Partial lot {lid} not found.") from e
            if (lot.item.sku or "").strip() not in family_skus:
                if parent_code_for_item(lot.item) != parent:
                    raise ReworkError(
                        f"Lot {lot.lot_number} is not in parent family {parent}."
                    )

            rem = lot_available_remnant_quantity(lot)
            max_use = round(min(rem, float(lot.quantity_remaining or 0)), 2)
            if max_use < 0.01:
                raise ReworkError(
                    f"Lot {lot.lot_number} has no available remnant to rework."
                )
            qty_raw = raw.get("quantity")
            if qty_raw is None or qty_raw == "":
                qty = max_use
            else:
                qty = float(qty_raw)
            qty = round(qty, 2)
            if qty <= 0:
                continue
            if qty > max_use + 1e-6:
                raise ReworkError(
                    f"Only {max_use:.2f} remnant available on {lot.lot_number}."
                )
            allocated.append((lot, qty))
            total += qty

        for raw in adjust_lines:
            try:
                lid = int(raw.get("lot_id"))
                qty = round(float(raw.get("quantity") or 0), 2)
            except (TypeError, ValueError) as e:
                raise ReworkError("Invalid strength-adjust lot.") from e
            if qty <= 0:
                continue
            try:
                lot = Lot.objects.select_related("item").get(pk=lid, status="accepted")
            except Lot.DoesNotExist as e:
                raise ReworkError(f"Adjust lot {lid} not found.") from e
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if qty > avail + 1e-6:
                raise ReworkError(
                    f"Only {avail:.2f} available on lot {lot.lot_number}."
                )
            allocated.append((lot, qty))
            total += qty

        total = round(total, 2)
        if total <= 0:
            raise ReworkError("Rework quantity must be greater than zero.")

        batch_number = generate_batch_number(batch_type="rework")
        now = timezone.now()
        batch = ProductionBatch.objects.create(
            batch_number=batch_number,
            batch_type="rework",
            finished_good_item=target_item,
            quantity_produced=total,
            quantity_actual=0.0,
            production_date=now,
            status="in_progress",
            notes=(
                f"Rework blend under parent {parent}"
                + (f"\n{(notes or '').strip()}" if (notes or "").strip() else "")
                + f"\nBy {actor}"
            ),
        )

        # Allocate only — quantity_remaining stays until Close (like batch tickets).
        for lot, qty in allocated:
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                item=lot.item,
                quantity_used=qty,
            )

        # Packaging / indirect materials — consume immediately (same as make tickets).
        for pkg in packaging_lines:
            try:
                lid = int(pkg.get("lot_id"))
                raw_qty = float(pkg.get("quantity_used") or pkg.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if raw_qty <= 0:
                continue
            try:
                lot = Lot.objects.select_related("item").exclude(status="rejected").get(pk=lid)
            except Lot.DoesNotExist as e:
                raise ReworkError(f"Packaging lot {lid} not found.") from e
            if (getattr(lot.item, "item_type", None) or "") != "indirect_material":
                raise ReworkError(
                    f"Lot {lot.lot_number} is not packaging (indirect material)."
                )
            quantity_used = _round_production_quantity_used(raw_qty, lot)
            if quantity_used <= 0:
                continue
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if quantity_used > avail + 1e-6:
                raise ReworkError(
                    f"Only {avail:.2f} available on packaging lot {lot.lot_number}."
                )
            before = float(lot.quantity_remaining or 0)
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                item=lot.item,
                quantity_used=quantity_used,
            )
            txn = InventoryTransaction.objects.create(
                transaction_type="indirect_material_consumption",
                lot=lot,
                quantity=-quantity_used,
                reference_number=batch_number,
                notes=f"Rework {batch_number} packaging",
            )
            log_lot_transaction(
                lot=lot,
                quantity_before=before,
                quantity_change=-quantity_used,
                transaction_type="indirect_material_consumption",
                reference_number=batch_number,
                reference_type="batch_number",
                transaction_id=txn.id,
                batch_id=batch.id,
                notes=f"Rework packaging by {actor}",
            )
            lot.quantity_remaining = _round_lot_qty_remaining(
                before - quantity_used, lot
            )
            lot.save()

    return {"batch": batch, "output_lot": None, "quantity": total}
