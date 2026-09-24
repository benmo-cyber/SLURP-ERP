"""
Rework: blend parent-family FG partials (optional strength adjust with RM lots)
into a new lot under a chosen pack SKU. Output goes on hold awaiting micro.
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
    ItemPackSize,
    Lot,
    ProductionBatch,
    ProductionBatchInput,
    ProductionBatchOutput,
)
from .pack_display import is_partial_lot


class ReworkError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def partial_lots_for_parent(parent_code: str) -> list[Lot]:
    """Accepted partial lots under a parent family with available qty."""
    skus = skus_for_parent_code(parent_code)
    if not skus:
        return []
    lots = (
        Lot.objects.filter(
            item__sku__in=skus,
            status="accepted",
            quantity_remaining__gt=0,
        )
        .select_related("item", "pack_size")
        .order_by("-received_date")
    )
    out = []
    for lot in lots:
        if not is_partial_lot(lot):
            continue
        avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
        if avail > 1e-6:
            out.append(lot)
    return out


def execute_rework(
    *,
    target_item: Item,
    partial_lines: list[dict[str, Any]],
    adjust_lines: list[dict[str, Any]] | None = None,
    notes: str = "",
    user=None,
) -> dict[str, Any]:
    """
    Blend selected parent-family partials (+ optional RM adjust lots) into a new
    on-hold lot under ``target_item``.

    ``partial_lines``: [{lot_id, quantity?}] — quantity defaults to available.
    ``adjust_lines``: [{lot_id, quantity}] — RM / other lots for strength adjust.
    """
    from .hold_services import ensure_open_hold_case
    from .views import generate_batch_number, generate_lot_number, log_lot_transaction

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

    with transaction.atomic():
        consumed: list[tuple[Lot, float]] = []
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
            if not is_partial_lot(lot):
                raise ReworkError(
                    f"Lot {lot.lot_number} is not a partial (below one full pack)."
                )
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            qty_raw = raw.get("quantity")
            if qty_raw is None or qty_raw == "":
                qty = avail
            else:
                qty = float(qty_raw)
            qty = round(qty, 2)
            if qty <= 0:
                continue
            if qty > avail + 1e-6:
                raise ReworkError(
                    f"Only {avail:.2f} available on partial {lot.lot_number}."
                )
            consumed.append((lot, qty))
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
            consumed.append((lot, qty))
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
            quantity_actual=total,
            production_date=now,
            status="closed",
            closed_date=now,
            notes=(
                f"Rework blend under parent {parent}"
                + (f"\n{(notes or '').strip()}" if (notes or "").strip() else "")
                + f"\nBy {actor}"
            ),
        )

        for lot, qty in consumed:
            before = float(lot.quantity_remaining or 0)
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                item=lot.item,
                quantity_used=qty,
            )
            txn = InventoryTransaction.objects.create(
                transaction_type="production_input",
                lot=lot,
                quantity=-qty,
                reference_number=batch_number,
                notes=f"Rework {batch_number} consume",
            )
            log_lot_transaction(
                lot=lot,
                quantity_before=before,
                quantity_change=-qty,
                transaction_type="production_input",
                reference_number=batch_number,
                reference_type="batch_number",
                transaction_id=txn.id,
                batch_id=batch.id,
                notes=f"Rework consume by {actor}",
            )
            lot.quantity_remaining = round(before - qty, 2)
            lot.save()

        pack_size = ItemPackSize.objects.filter(
            item=target_item, is_default=True, is_active=True
        ).first()
        out_lot = Lot.objects.create(
            lot_number=generate_lot_number(),
            item=target_item,
            pack_size=pack_size,
            quantity=total,
            quantity_remaining=total,
            quantity_on_hold=total,
            received_date=now,
            manufacture_date=now,
            status="on_hold",
            on_hold=True,
            short_reason=f"Rework {batch_number}"[:255],
        )
        ProductionBatchOutput.objects.create(
            batch=batch,
            lot=out_lot,
            quantity_produced=total,
        )
        out_txn = InventoryTransaction.objects.create(
            transaction_type="production_output",
            lot=out_lot,
            quantity=total,
            reference_number=batch_number,
            notes=f"Rework {batch_number} output",
        )
        log_lot_transaction(
            lot=out_lot,
            quantity_before=0.0,
            quantity_change=total,
            transaction_type="production_output",
            reference_number=batch_number,
            reference_type="batch_number",
            transaction_id=out_txn.id,
            batch_id=batch.id,
            notes=f"Rework output by {actor}",
        )
        ensure_open_hold_case(
            out_lot,
            user=user,
            kind="awaiting_micro",
            summary=f"Rework {batch_number} — awaiting micro/QC",
            initial_note=(
                f"Rework blend into {target_item.sku}. "
                f"Parent family {parent}. Qty {total}."
            ),
        )

    return {"batch": batch, "output_lot": out_lot, "quantity": total}
