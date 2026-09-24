"""
Shared MAKE-flow services: Create batch ticket → Close → Reverse.

Used by DRF ViewSets and slurp_ui Django templates so production/repack rules live in one place.
"""
from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from datetime import datetime, time as dt_time
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .lot_display_quantities import compute_lot_quantity_breakdown
from .mass_quantity import convert_mass_uom, normalize_mass_quantity
from .models import (
    InventoryTransaction,
    Item,
    ItemPackSize,
    Lot,
    LotTransactionLog,
    ProductionBatch,
    ProductionBatchInput,
    ProductionBatchOutput,
    ProductionLog,
)
from .pack_display import resolve_pack_size

logger = logging.getLogger(__name__)

_QUANTITY_TOLERANCE = 0.02
_MASS_UOMS = frozenset({"lbs", "lb", "kg"})


def net_yield_native(batch: ProductionBatch) -> float | None:
    """
    Net yield after spill/waste for display / PDF.

    If wastes+spills already explain ticket−actual (proper close), ``quantity_actual``
    is already net — do not subtract again. Otherwise subtract losses from actual
    (common when actual is left at ticket and spill/waste are recorded separately).
    """
    if batch.quantity_actual is None:
        return None
    actual = float(batch.quantity_actual or 0)
    ticket = float(batch.quantity_produced or 0)
    loss = float(batch.wastes or 0) + float(batch.spills or 0)
    if loss <= 0:
        return actual
    shortfall = max(0.0, ticket - actual)
    if shortfall > 0.05 and abs(loss - shortfall) <= 0.05:
        return actual
    return max(0.0, actual - loss)


def _norm_mass_uom(uom: str | None) -> str:
    u = (uom or "lbs").strip().lower()
    if u in ("lb", "lbs"):
        return "lbs"
    return u


def _convert_item_mass(qty: float, from_uom: str | None, to_uom: str | None) -> float:
    """Convert mass between lbs/kg; pass through when UoMs match or are non-mass."""
    f = _norm_mass_uom(from_uom)
    t = _norm_mass_uom(to_uom)
    if f == t:
        return float(qty)
    if f in ("lbs", "kg") and t in ("lbs", "kg"):
        return float(convert_mass_uom(qty, f, t))
    return float(qty)


def pack_units_for_mass(item: Item | None, mass_qty: float, mass_uom: str | None) -> float | None:
    """
    How many packs/jugs ``mass_qty`` fills for ``item`` (e.g. 440 lbs / 8 lb = 55).

    Returns None when pack size is unknown or not mass-comparable.
    """
    if item is None or mass_qty <= 0:
        return None
    pack_qty, pack_uom = resolve_pack_size(item=item)
    if not pack_qty or pack_qty <= 0:
        return None
    pu = _norm_mass_uom(pack_uom or item.unit_of_measure)
    mu = _norm_mass_uom(mass_uom or item.unit_of_measure)
    if pu not in ("lbs", "kg") or mu not in ("lbs", "kg"):
        # Non-mass packs (ea): treat mass_qty as unit count already
        if pu in ("ea", "each", "pcs") or mu in ("ea", "each", "pcs"):
            return float(mass_qty)
        return None
    mass_in_pack_uom = _convert_item_mass(mass_qty, mu, pu)
    return mass_in_pack_uom / float(pack_qty)


def _is_plant_utility(item) -> bool:
    return bool(item and getattr(item, "plant_utility", False))


def _resolve_batch_input_row(input_data: dict, *, require_available: bool = True):
    """
    Resolve a create/adjust input dict to (lot|None, item, quantity_used).

    Accepts either lot_id (normal RM) or item_id for plant_utility items.
    """
    from .views import _round_production_quantity_used

    lot_id = input_data.get("lot_id")
    item_id = input_data.get("item_id")
    raw_quantity = float(input_data.get("quantity_used", 0) or 0)

    if lot_id:
        try:
            lot = Lot.objects.select_related("item").get(id=lot_id)
        except Lot.DoesNotExist as e:
            raise MakeFlowError(f"Lot with id {lot_id} not found", status_code=404) from e
        item = lot.item
        if _is_plant_utility(item):
            raise MakeFlowError(
                f"{item.sku} is a plant utility — use item_id quantity, not a lot."
            )
        quantity_used = _round_production_quantity_used(raw_quantity, lot)
        if quantity_used <= 0:
            raise MakeFlowError("Invalid input data: lot_id and quantity_used are required")
        if require_available:
            available = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if quantity_used > available + 1e-6:
                raise MakeFlowError(
                    f"Insufficient quantity in lot {lot.lot_number}. "
                    f"Available: {available}, Requested: {quantity_used}"
                )
        return lot, item, quantity_used

    if item_id:
        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist as e:
            raise MakeFlowError(f"Item with id {item_id} not found", status_code=404) from e
        if not _is_plant_utility(item):
            raise MakeFlowError(
                f"{item.sku} requires a lot allocation (not marked plant utility)."
            )
        from .mass_quantity import snap_stored_batch_input_quantity

        quantity_used = snap_stored_batch_input_quantity(
            raw_quantity, getattr(item, "unit_of_measure", None)
        )
        if quantity_used <= 0:
            raise MakeFlowError("Invalid input data: item_id and quantity_used are required")
        return None, item, quantity_used

    raise MakeFlowError("Invalid input data: lot_id or plant-utility item_id is required")


class MakeFlowError(Exception):
    """User-facing MAKE flow error with optional HTTP-ish status code and extra response fields."""

    def __init__(self, message: str, status_code: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def _payload_copy(data: dict | Any) -> dict:
    payload = deepcopy(data) if data is not None else {}
    if hasattr(payload, "lists"):
        payload = {k: (v[0] if len(v) == 1 else v) for k, v in payload.lists()}
    elif hasattr(payload, "copy"):
        payload = payload.copy()
    return dict(payload)


def _parse_production_date(value: Any):
    if value is None:
        return timezone.now()
    if not isinstance(value, str):
        return value
    parsed = parse_datetime(value)
    if not parsed:
        date_obj = parse_date(value)
        if date_obj:
            local_tz = timezone.get_current_timezone()
            parsed = local_tz.localize(datetime.combine(date_obj, dt_time(12, 0, 0)))
    if parsed:
        return parsed
    return timezone.now()


def create_batch_ticket(user, data: dict) -> ProductionBatch:
    """
    Create a production or repack batch ticket with inputs (and optional indirect materials).

    ``data`` keys: batch_type, finished_good_item_id, quantity_produced, production_date,
    status, batch_ticket_mass_unit, recipe_snapshot, notes, inputs, indirect_materials,
    work_in_partials, outputs, batch_number (optional), critical_control_point (optional CCP pk).
    """
    from .serializers import ProductionBatchSerializer
    from .views import (
        _round_lot_qty_remaining,
        _round_production_quantity_used,
        generate_batch_number,
        log_lot_transaction,
    )

    payload = _payload_copy(data)
    inputs_data = payload.pop("inputs", []) or []
    outputs_data = payload.pop("outputs", []) or []
    indirect_materials_data = payload.pop("indirect_materials", []) or []
    work_in_partials_data = payload.pop("work_in_partials", []) or []
    batch_type = payload.get("batch_type", "production")

    if isinstance(inputs_data, dict):
        inputs_data = [inputs_data]
    if isinstance(outputs_data, dict):
        outputs_data = [outputs_data]
    if isinstance(indirect_materials_data, dict):
        indirect_materials_data = [indirect_materials_data]

    if "production_date" in payload:
        payload["production_date"] = _parse_production_date(payload.get("production_date"))

    if "batch_number" not in payload or not payload.get("batch_number"):
        payload["batch_number"] = generate_batch_number(batch_type)
    elif ProductionBatch.objects.filter(batch_number=payload["batch_number"]).exists():
        payload["batch_number"] = generate_batch_number(batch_type)

    if not payload.get("finished_good_item_id"):
        if batch_type == "production":
            raise MakeFlowError("finished_good_item_id is required for production batches")

    if batch_type == "repack":
        if not inputs_data:
            raise MakeFlowError("Repack batches require at least one input lot")
        try:
            first_lot = Lot.objects.select_related("item").get(id=inputs_data[0]["lot_id"])
            source_item = first_lot.item
            for input_data in inputs_data:
                lot = Lot.objects.select_related("item").get(id=input_data["lot_id"])
                if lot.item_id != source_item.id:
                    raise MakeFlowError(
                        "All input lots must be for the same source SKU in a repack batch"
                    )
            # Target SKU (output): explicit finished_good_item_id, else same as source
            target_id = payload.get("finished_good_item_id")
            if target_id:
                try:
                    target_item = Item.objects.get(id=int(target_id))
                except (Item.DoesNotExist, TypeError, ValueError) as e:
                    raise MakeFlowError(
                        "Invalid finished_good_item_id for repack target SKU", status_code=404
                    ) from e
            else:
                target_item = source_item
                payload["finished_good_item_id"] = source_item.id
            payload["finished_good_item_id"] = target_item.id
        except Lot.DoesNotExist as e:
            raise MakeFlowError("Invalid lot ID in inputs", status_code=404) from e

    quantity_produced_from_request = normalize_mass_quantity(
        round(float(payload.get("quantity_produced", 0)), 2)
    )
    total_input_quantity_in_lbs = 0.0
    total_input_quantity_native = 0.0
    resolved_inputs = []

    for input_data in inputs_data:
        lot, item, quantity_used = _resolve_batch_input_row(input_data, require_available=True)
        quantity_used_in_lbs = quantity_used
        if (item.unit_of_measure or "").lower() == "kg":
            quantity_used_in_lbs = convert_mass_uom(quantity_used, "kg", "lbs")
        total_input_quantity_in_lbs += quantity_used_in_lbs
        total_input_quantity_native += quantity_used
        resolved_inputs.append((lot, item, quantity_used))

    if batch_type == "repack":
        target_item = Item.objects.get(id=payload["finished_good_item_id"])
        target_uom = target_item.unit_of_measure or "lbs"
        source_uom = resolved_inputs[0][1].unit_of_measure if resolved_inputs else target_uom
        # Convert consumed source mass into target native UoM (cross-pack kg↔lbs)
        total_in_target_uom = 0.0
        for _lot, item, qty in resolved_inputs:
            total_in_target_uom += _convert_item_mass(
                qty, item.unit_of_measure, target_uom
            )
        total_in_target_uom = normalize_mass_quantity(round(total_in_target_uom, 2))
        quantity_produced = total_in_target_uom
        if abs(total_in_target_uom - quantity_produced_from_request) > _QUANTITY_TOLERANCE:
            raise MakeFlowError(
                f"Quantity mismatch: Consumed input equals {total_in_target_uom:.2f} "
                f"{_norm_mass_uom(target_uom)} toward target {target_item.sku}, but quantity "
                f"to produce is {quantity_produced_from_request:.2f} "
                f"{_norm_mass_uom(target_uom)}"
            )
        # Soft note when source/target differ
        if target_item.id != resolved_inputs[0][1].id:
            note = (
                f"[REPACK {resolved_inputs[0][1].sku} → {target_item.sku}; "
                f"source {_norm_mass_uom(source_uom)} → target {_norm_mass_uom(target_uom)}]"
            )
            existing_notes = (payload.get("notes") or "").strip()
            payload["notes"] = f"{existing_notes}\n{note}".strip() if existing_notes else note
    else:
        total_rounded = normalize_mass_quantity(round(total_input_quantity_in_lbs, 2))
        if abs(total_input_quantity_in_lbs - quantity_produced_from_request) > _QUANTITY_TOLERANCE:
            raise MakeFlowError(
                f"Quantity mismatch: Total quantity used ({total_input_quantity_in_lbs:.2f} lbs) "
                f"must equal quantity to produce ({quantity_produced_from_request:.2f} lbs)"
            )
        quantity_produced = total_rounded
    payload["quantity_produced"] = quantity_produced

    if work_in_partials_data:
        partials_json = json.dumps(work_in_partials_data)
        if payload.get("notes"):
            payload["notes"] = f"{payload['notes']}\n[WORK_IN_PARTIALS:{partials_json}]"
        else:
            payload["notes"] = f"[WORK_IN_PARTIALS:{partials_json}]"

    serializer = ProductionBatchSerializer(data=payload)
    if not serializer.is_valid():
        logger.error("Batch serializer validation failed: %s", serializer.errors)
        raise MakeFlowError("", extra={"_serializer_errors": serializer.errors})

    batch = serializer.save()

    try:
        for lot, item, quantity_used in resolved_inputs:
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                item=item,
                quantity_used=quantity_used,
            )

        if batch_type == "repack":
            target = batch.finished_good_item
            target_uom = target.unit_of_measure if target else "lbs"
            converted = 0.0
            for _lot, item, qty in resolved_inputs:
                converted += _convert_item_mass(qty, item.unit_of_measure, target_uom)
            converted = normalize_mass_quantity(round(converted, 2))
            if abs(converted - quantity_produced) > _QUANTITY_TOLERANCE:
                raise MakeFlowError(
                    f"Quantity mismatch: Total quantity used ({converted:.2f} "
                    f"{_norm_mass_uom(target_uom)}) must equal quantity to produce "
                    f"({quantity_produced:.2f} {_norm_mass_uom(target_uom)})"
                )
        elif abs(total_input_quantity_in_lbs - quantity_produced) > _QUANTITY_TOLERANCE:
            raise MakeFlowError(
                f"Quantity mismatch: Total quantity used ({total_input_quantity_in_lbs:.2f} lbs) "
                f"must equal quantity to produce ({quantity_produced:.2f} lbs)"
            )

        if batch_type == "repack" and outputs_data:
            for output_data in outputs_data:
                lot_id = output_data.get("lot_id")
                output_qty = float(output_data.get("quantity_produced", 0))
                if not lot_id or output_qty <= 0:
                    raise MakeFlowError(
                        "Invalid output data: lot_id and quantity_produced are required"
                    )
                try:
                    lot = Lot.objects.get(id=lot_id)
                except Lot.DoesNotExist as e:
                    raise MakeFlowError(f"Lot with id {lot_id} not found", status_code=404) from e
                ProductionBatchOutput.objects.create(
                    batch=batch,
                    lot=lot,
                    quantity_produced=output_qty,
                )
                txn = InventoryTransaction.objects.create(
                    transaction_type="repack_output",
                    lot=lot,
                    quantity=output_qty,
                    notes=f"Repack batch {batch.batch_number} output",
                    reference_number=batch.batch_number,
                )
                log_lot_transaction(
                    lot=lot,
                    quantity_before=0.0,
                    quantity_change=output_qty,
                    transaction_type="repack_output",
                    reference_number=batch.batch_number,
                    reference_type="batch_number",
                    transaction_id=txn.id,
                    batch_id=batch.id,
                    notes=(
                        f"Repack batch {batch.batch_number} output - "
                        "Distributed item relabeled/repacked"
                    ),
                )
        elif batch_type == "production":
            for output_data in outputs_data:
                lot_id = output_data.get("lot_id")
                output_qty = round(float(output_data.get("quantity_produced", 0)), 2)
                if lot_id and output_qty > 0:
                    try:
                        lot = Lot.objects.get(id=lot_id)
                        ProductionBatchOutput.objects.create(
                            batch=batch,
                            lot=lot,
                            quantity_produced=output_qty,
                        )
                        InventoryTransaction.objects.create(
                            transaction_type="production_output",
                            lot=lot,
                            quantity=round(output_qty, 2),
                            notes=f"Batch {batch.batch_number} output",
                            reference_number=batch.batch_number,
                        )
                    except Lot.DoesNotExist:
                        pass

        for indirect_data in indirect_materials_data:
            lot_id = indirect_data.get("lot_id")
            raw_qty = float(indirect_data.get("quantity_used", 0))
            if not lot_id or raw_qty <= 0:
                continue
            try:
                lot = Lot.objects.get(id=lot_id)
            except Lot.DoesNotExist as e:
                raise MakeFlowError(
                    f"Indirect material lot with id {lot_id} not found", status_code=404
                ) from e
            if lot.item.item_type != "indirect_material":
                continue
            quantity_used = _round_production_quantity_used(raw_qty, lot)
            if quantity_used <= 0:
                continue
            max_use = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if quantity_used > max_use + 1e-6:
                raise MakeFlowError(
                    f"Insufficient quantity in indirect material lot {lot.lot_number}. "
                    f"Available: {max_use}, Requested: {quantity_used}"
                )
            ProductionBatchInput.objects.create(
                batch=batch,
                lot=lot,
                quantity_used=quantity_used,
            )
            quantity_before = lot.quantity_remaining
            txn = InventoryTransaction.objects.create(
                transaction_type="indirect_material_consumption",
                lot=lot,
                quantity=-quantity_used,
                notes=(
                    f"{batch.get_batch_type_display()} batch {batch.batch_number} - "
                    "indirect material consumption"
                ),
                reference_number=batch.batch_number,
            )
            log_lot_transaction(
                lot=lot,
                quantity_before=quantity_before,
                quantity_change=-quantity_used,
                transaction_type="indirect_material_consumption",
                reference_number=batch.batch_number,
                reference_type="batch_number",
                transaction_id=txn.id,
                batch_id=batch.id,
                notes=(
                    f"Indirect material consumed in {batch.get_batch_type_display()} "
                    f"batch {batch.batch_number}"
                ),
            )
            lot.quantity_remaining = _round_lot_qty_remaining(
                lot.quantity_remaining - quantity_used, lot
            )
            lot.save()
    except MakeFlowError:
        batch.delete()
        raise
    except Exception as e:
        batch.delete()
        raise MakeFlowError(f"Failed to create batch ticket: {e}") from e

    return batch


def adjust_batch_inputs(batch: ProductionBatch, data: dict) -> ProductionBatch:
    """
    Replace batch inputs and optionally update quantity_produced.

    Validates total input quantity equals quantity_produced (production: lbs; repack: native UoM).
    """
    from .views import _round_production_quantity_used

    inputs_data = data.get("inputs")
    if inputs_data is None:
        return batch
    if isinstance(inputs_data, dict):
        inputs_data = [inputs_data]

    quantity_produced = data.get("quantity_produced")
    if quantity_produced is not None:
        quantity_produced = normalize_mass_quantity(round(float(quantity_produced), 2))

    for existing_input in batch.inputs.select_related("lot", "item").all():
        resolved = existing_input.resolved_item() if hasattr(existing_input, "resolved_item") else (
            existing_input.item or (existing_input.lot.item if existing_input.lot_id else None)
        )
        if resolved and resolved.item_type == "indirect_material":
            # Keep packaging / IM rows; adjust form only replaces product lots
            continue
        lot = existing_input.lot
        if lot is not None:
            old_transactions = InventoryTransaction.objects.filter(
                lot=lot,
                reference_number=batch.batch_number,
                transaction_type__in=["production_input", "repack_input"],
                quantity__lt=0,
            ).order_by("-transaction_date")
            for old_txn in old_transactions:
                if abs(abs(old_txn.quantity) - existing_input.quantity_used) < 0.01:
                    lot.quantity_remaining = round(
                        lot.quantity_remaining + existing_input.quantity_used, 2
                    )
                    lot.save()
                    break
            for old_txn in list(old_transactions):
                if abs(abs(old_txn.quantity) - existing_input.quantity_used) < 0.01:
                    old_txn.delete()
            LotTransactionLog.objects.filter(
                lot=lot,
                reference_number=batch.batch_number,
                transaction_type__in=["production_input", "repack_input"],
                batch_id=batch.id,
            ).delete()
        existing_input.delete()

    total_lbs = 0.0
    total_native = 0.0
    total_target_uom = 0.0
    item_unit = None
    target_uom = None
    if batch.batch_type == "repack" and batch.finished_good_item_id:
        target_uom = batch.finished_good_item.unit_of_measure or "lbs"

    for input_data in inputs_data:
        try:
            lot, item, quantity_used = _resolve_batch_input_row(
                input_data, require_available=True
            )
        except MakeFlowError:
            # Skip empty / zero rows from the form
            raw_quantity = float(input_data.get("quantity_used", 0) or 0)
            if raw_quantity <= 0:
                continue
            raise
        # Skip re-adding indirect materials here — adjust form is product lots only
        if item and item.item_type == "indirect_material":
            continue
        ProductionBatchInput.objects.create(
            batch=batch,
            lot=lot,
            item=item,
            quantity_used=quantity_used,
        )
        if batch.batch_type == "repack":
            item_unit = item.unit_of_measure
            total_target_uom += _convert_item_mass(
                quantity_used, item.unit_of_measure, target_uom or item.unit_of_measure
            )
        qty_lbs = quantity_used
        if (item.unit_of_measure or "").lower() == "kg":
            qty_lbs = convert_mass_uom(quantity_used, "kg", "lbs")
        total_lbs += qty_lbs
        total_native += quantity_used

    target_qty = quantity_produced if quantity_produced is not None else batch.quantity_produced
    if batch.batch_type == "repack":
        total_target_uom = normalize_mass_quantity(round(total_target_uom, 2))
        if abs(total_target_uom - target_qty) > _QUANTITY_TOLERANCE:
            unit = _norm_mass_uom(target_uom or item_unit or "lbs")
            raise MakeFlowError(
                f"Quantity mismatch: Total quantity used ({total_target_uom:.2f} {unit}) "
                f"must equal quantity to produce ({target_qty:.2f} {unit})"
            )
        batch.quantity_produced = total_target_uom
        batch.save(update_fields=["quantity_produced"])
        return batch
    elif abs(total_lbs - target_qty) > _QUANTITY_TOLERANCE:
        raise MakeFlowError(
            f"Quantity mismatch: Total quantity used ({total_lbs:.2f} lbs) "
            f"must equal quantity to produce ({target_qty:.2f} lbs)"
        )

    if quantity_produced is not None:
        batch.quantity_produced = quantity_produced
        batch.save(update_fields=["quantity_produced"])

    return batch


def _extract_work_in_partials(batch: ProductionBatch, work_in_partials_data: list | None) -> list:
    if work_in_partials_data:
        return work_in_partials_data
    if not batch.notes:
        return []
    match = re.search(r"\[WORK_IN_PARTIALS:(.*?)\]", batch.notes)
    if not match:
        return []
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return []


def _batch_is_relabel(batch: ProductionBatch) -> bool:
    """Same-SKU / same-container relabel (no packaging, no pack-change)."""
    notes = (batch.notes or "").upper()
    if "[RELABEL" in notes:
        return True
    if batch.batch_type != "repack" or not batch.finished_good_item_id:
        return False
    product_inputs = []
    for inp in batch.inputs.select_related("lot__item", "item").all():
        item = inp.resolved_item()
        if item is None:
            continue
        if item.item_type == "indirect_material":
            return False
        product_inputs.append(item.id)
    if not product_inputs:
        return False
    return all(iid == batch.finished_good_item_id for iid in product_inputs)


def _primary_product_input_lot(batch: ProductionBatch):
    """First non-indirect input lot — source of inbound PO / vendor-lot pedigree."""
    for inp in batch.inputs.select_related("lot__item", "item").all():
        if not inp.lot_id:
            continue
        item = inp.resolved_item() if hasattr(inp, "resolved_item") else (
            inp.item or (inp.lot.item if inp.lot_id else None)
        )
        if item is not None and getattr(item, "item_type", "") == "indirect_material":
            continue
        return inp.lot
    return None


def _copy_inbound_traceability(dest_lot, src_lot, *, save: bool = True) -> list[str]:
    """
    Carry PO #, vendor lot #, and manufacture date from inbound source → output lot.
    Does not overwrite values already set on dest.
    """
    if dest_lot is None or src_lot is None:
        return []
    fields: list[str] = []
    if not (dest_lot.po_number or "").strip() and (src_lot.po_number or "").strip():
        dest_lot.po_number = (src_lot.po_number or "").strip()
        fields.append("po_number")
    if not (dest_lot.vendor_lot_number or "").strip() and (
        src_lot.vendor_lot_number or ""
    ).strip():
        dest_lot.vendor_lot_number = (src_lot.vendor_lot_number or "").strip()
        fields.append("vendor_lot_number")
    if dest_lot.manufacture_date is None and src_lot.manufacture_date is not None:
        dest_lot.manufacture_date = src_lot.manufacture_date
        fields.append("manufacture_date")
    if save and fields:
        dest_lot.save(update_fields=fields)
    return fields


def close_batch_ticket(batch: ProductionBatch, user, data: dict) -> ProductionBatch:
    """
    Close an open batch: apply close fields, validate wastes/spills, run inventory side effects.

    ``data`` may include quantity_actual, wastes, spills, variance, notes, closed_date,
    work_in_partials, and ``_prior_status`` (must not be ``closed``).
    """
    from .serializers import ProductionBatchSerializer
    from .views import (
        _expiration_datetime_for_fg_output,
        _round_lot_qty_remaining,
        _round_production_quantity_used,
        generate_lot_number,
        log_lot_transaction,
        log_production_batch_closure,
    )

    prior_status = data.get("_prior_status")
    if prior_status == "closed":
        raise MakeFlowError("Batch is already closed.")

    allow_early = bool(data.get("allow_early_close"))
    pd = getattr(batch, "production_date", None)
    if pd and not allow_early:
        prod_day = (
            timezone.localtime(pd).date()
            if timezone.is_aware(pd)
            else (pd.date() if hasattr(pd, "date") else pd)
        )
        if prod_day > timezone.localdate():
            raise MakeFlowError(
                f"Cannot close before production date ({prod_day.isoformat()}). "
                "Enable God mode (staff) to close early, or wait until that date."
            )

    close_payload: dict[str, Any] = {"status": "closed"}
    for key in ("quantity_actual", "wastes", "spills", "variance", "notes", "closed_date"):
        if key in data:
            close_payload[key] = data[key]

    if "closed_date" not in close_payload or not close_payload.get("closed_date"):
        close_payload["closed_date"] = timezone.now()
    elif isinstance(close_payload["closed_date"], str):
        parsed = parse_datetime(close_payload["closed_date"])
        if not parsed:
            parsed = parse_date(close_payload["closed_date"])
            if parsed:
                local_tz = timezone.get_current_timezone()
                parsed = local_tz.localize(datetime.combine(parsed, dt_time(12, 0, 0)))
        close_payload["closed_date"] = parsed or timezone.now()

    if len(close_payload) > 1:
        serializer = ProductionBatchSerializer(instance=batch, data=close_payload, partial=True)
        try:
            serializer.is_valid(raise_exception=True)
            batch = serializer.save()
        except Exception as e:
            detail = getattr(e, "detail", None)
            if detail is not None:
                raise MakeFlowError("", extra={"_serializer_errors": detail}) from e
            raise MakeFlowError(f"Failed to close batch: {e}") from e

    if not batch.closed_date:
        batch.closed_date = timezone.now()
        batch.save(update_fields=["closed_date"])

    work_in_partials_data = data.get("work_in_partials")
    final_work_in_partials = _extract_work_in_partials(batch, work_in_partials_data)

    log_production_batch_closure(batch, notes=f"Batch {batch.batch_number} closed")

    batch_type_label = "repack" if batch.batch_type == "repack" else "production"
    input_transaction_type = "repack_input" if batch.batch_type == "repack" else "production_input"

    for batch_input in batch.inputs.select_related("lot__item", "item").all():
        lot = batch_input.lot
        item = batch_input.resolved_item()
        if lot is None or _is_plant_utility(item):
            continue
        if item and item.item_type == "indirect_material":
            continue
        qty = batch_input.quantity_used
        rounded_qty = _round_production_quantity_used(qty, lot)
        quantity_before = lot.quantity_remaining
        if lot.quantity_remaining < rounded_qty:
            continue
        lot.quantity_remaining = _round_lot_qty_remaining(
            lot.quantity_remaining - rounded_qty, lot
        )
        lot.save()
        InventoryTransaction.objects.create(
            transaction_type=input_transaction_type,
            lot=lot,
            quantity=-rounded_qty,
            notes=f"{batch_type_label.capitalize()} batch {batch.batch_number} input (closed)",
            reference_number=batch.batch_number,
        )
        log_lot_transaction(
            lot=lot,
            quantity_before=quantity_before,
            quantity_change=-rounded_qty,
            transaction_type=input_transaction_type,
            reference_number=batch.batch_number,
            reference_type="batch_number",
            transaction_id=None,
            batch_id=batch.id,
            notes=f"Used in {batch_type_label} batch {batch.batch_number} (closed)",
        )

    if batch.outputs.exists():
        existing_output = batch.outputs.first()
        logger.info(
            "Batch %s already has output lot %s",
            batch.batch_number,
            existing_output.lot.lot_number if existing_output else "unknown",
        )
        return batch

    if batch.batch_type == "production":
        # Inventory = net yield after spill/waste (same as PDF / batch detail).
        # When quantity_actual is left at ticket and losses are recorded separately,
        # net_yield_native subtracts them; when actual is already net, it leaves it.
        net = net_yield_native(batch)
        if net is not None:
            main_output_qty = round(max(0.0, float(net)), 2)
        else:
            base_quantity = (
                batch.quantity_actual
                if batch.quantity_actual and batch.quantity_actual > 0
                else batch.quantity_produced
            )
            main_output_qty = round(max(0.0, float(base_quantity)), 2)
        item = batch.finished_good_item
        closed_dt = batch.closed_date or timezone.now()
        from .formula_resolve import formula_for_batch

        output_expiration = _expiration_datetime_for_fg_output(
            item, closed_dt, formula=formula_for_batch(batch)
        )

        partial_quantities = []
        partial_lots_to_delete = []
        if final_work_in_partials:
            for partial_data in final_work_in_partials:
                partial_lot_id = partial_data.get("lot_id")
                if partial_lot_id:
                    try:
                        from .formula_ingredient import parent_code_for_item

                        partial_lot = Lot.objects.select_related("item").get(
                            id=partial_lot_id, status="accepted"
                        )
                        same_item = partial_lot.item_id == item.id
                        same_parent = (
                            parent_code_for_item(partial_lot.item)
                            == parent_code_for_item(item)
                            and parent_code_for_item(item)
                        )
                        if not same_item and not same_parent:
                            continue
                        if partial_lot.quantity_remaining > 0:
                            partial_qty = partial_lot.quantity_remaining
                            partial_quantities.append(partial_qty)
                            partial_lots_to_delete.append(partial_lot)
                    except Lot.DoesNotExist:
                        pass

        total_partial_qty = sum(partial_quantities)
        combined_output_quantity = round(main_output_qty + total_partial_qty, 2)
        lot_number = generate_lot_number()
        pack_size = ItemPackSize.objects.filter(
            item=item, is_default=True, is_active=True
        ).first()

        new_lot = Lot.objects.create(
            lot_number=lot_number,
            item=item,
            pack_size=pack_size,
            quantity=combined_output_quantity,
            quantity_remaining=combined_output_quantity,
            quantity_on_hold=combined_output_quantity,
            received_date=closed_dt,
            manufacture_date=closed_dt,
            expiration_date=output_expiration,
            status="on_hold",
            on_hold=True,
        )

        ProductionBatchOutput.objects.create(
            batch=batch,
            lot=new_lot,
            quantity_produced=combined_output_quantity,
        )

        try:
            from .hold_services import ensure_open_hold_case, parse_batch_qc_notes, parse_qc_float

            qc_param = (data.get("qc_parameter") or data.get("qc_parameters") or "").strip()
            qc_actual = data.get("qc_actual")
            qc_initials = (data.get("qc_initials") or "").strip()
            if not qc_param and not qc_actual and not qc_initials:
                parsed = parse_batch_qc_notes(batch.notes)
                qc_param = parsed["parameter"]
                qc_actual = parsed["actual_value"]
                qc_initials = parsed["initials"]
            qc_val = parse_qc_float(qc_actual)
            summary = "Awaiting micro/QC results"
            if qc_param and qc_val is not None:
                summary = f"Awaiting micro/QC — {qc_param}: {qc_val:g}"
            elif qc_param:
                summary = f"Awaiting micro/QC — {qc_param}"

            ensure_open_hold_case(
                new_lot,
                user=user,
                kind="awaiting_micro",
                summary=summary,
                initial_note=(
                    f"Manufactured lot from batch {batch.batch_number} "
                    "placed on hold pending micro/QC release."
                ),
                qc_parameter_name=qc_param,
                qc_result_value=qc_val,
                qc_initials=qc_initials,
            )
        except Exception:
            logger.exception(
                "Failed to open awaiting_micro hold case for lot %s (batch %s)",
                new_lot.lot_number,
                batch.batch_number,
            )

        _uom = getattr(item, "unit_of_measure", None) or "lbs"
        doc_bits = []
        if (batch.wastes or 0) > 0:
            doc_bits.append(f"wastes {batch.wastes} {_uom} documented")
        if (batch.spills or 0) > 0:
            doc_bits.append(f"spills {batch.spills} {_uom} documented")
        doc_suffix = f" — {', '.join(doc_bits)}" if doc_bits else ""
        InventoryTransaction.objects.create(
            transaction_type="production_output",
            lot=new_lot,
            quantity=round(main_output_qty, 2),
            notes=(
                f"Production batch {batch.batch_number} output "
                f"({main_output_qty} {_uom} produced{doc_suffix})"
            ),
            reference_number=batch.batch_number,
        )

        for partial_lot, partial_qty in zip(partial_lots_to_delete, partial_quantities):
            InventoryTransaction.objects.create(
                transaction_type="production_output",
                lot=new_lot,
                quantity=round(partial_qty, 2),
                notes=(
                    f"Production batch {batch.batch_number} - worked in partial "
                    f"from lot {partial_lot.lot_number}"
                ),
                reference_number=batch.batch_number,
            )
            InventoryTransaction.objects.create(
                transaction_type="adjustment",
                lot=partial_lot,
                quantity=round(-partial_qty, 2),
                notes=f"Worked into batch {batch.batch_number}",
                reference_number=batch.batch_number,
            )
            partial_lot.delete()

        work_in_note = (
            f", worked in {total_partial_qty} lbs from partials" if total_partial_qty > 0 else ""
        )
        logger.info(
            "Created output lot %s for batch %s: item=%s, quantity=%s lbs "
            "(produced: %s%s), status=%s",
            new_lot.lot_number,
            batch.batch_number,
            item.sku,
            combined_output_quantity,
            main_output_qty,
            work_in_note,
            new_lot.status,
        )

    elif batch.batch_type == "repack":
        # Prefer quantity_actual (close form); fall back to converted product inputs.
        # Spill/waste document shortfall vs ticket — they do not shrink this further.
        target_item = batch.finished_good_item
        target_uom = (target_item.unit_of_measure if target_item else None) or "lbs"
        input_converted = 0.0
        for input_item in batch.inputs.select_related("lot__item", "item").all():
            resolved = input_item.resolved_item() if hasattr(input_item, "resolved_item") else (
                input_item.item or (input_item.lot.item if input_item.lot_id else None)
            )
            if resolved and resolved.item_type == "indirect_material":
                continue
            src_uom = (resolved.unit_of_measure if resolved else None) or target_uom
            input_converted += _convert_item_mass(
                float(input_item.quantity_used or 0), src_uom, target_uom
            )
        input_converted = round(input_converted, 2)
        if batch.quantity_actual is not None and float(batch.quantity_actual) > 0:
            output_quantity = round(float(batch.quantity_actual), 2)
        else:
            output_quantity = input_converted
        item = target_item
        closed_dt = batch.closed_date or timezone.now()
        from .formula_resolve import formula_for_batch

        output_expiration = _expiration_datetime_for_fg_output(
            item, closed_dt, formula=formula_for_batch(batch)
        )

        # Prefer target SKU pack size (e.g. 8 lb jug), not source drum pack
        pack_size = ItemPackSize.objects.filter(
            item=item, is_default=True, is_active=True
        ).first()
        if pack_size is None:
            pack_size = ItemPackSize.objects.filter(item=item, is_active=True).first()

        lot_number = generate_lot_number()
        is_relabel = _batch_is_relabel(batch)
        src_lot = _primary_product_input_lot(batch)
        if is_relabel:
            # Same container — source already accepted; do not gate sales behind micro.
            new_lot = Lot.objects.create(
                lot_number=lot_number,
                item=item,
                pack_size=pack_size,
                quantity=output_quantity,
                quantity_remaining=output_quantity,
                quantity_on_hold=0.0,
                received_date=closed_dt,
                expiration_date=output_expiration,
                status="accepted",
                on_hold=False,
            )
            _copy_inbound_traceability(new_lot, src_lot)
            if new_lot.manufacture_date is None:
                new_lot.manufacture_date = closed_dt
                new_lot.save(update_fields=["manufacture_date"])
            # Supplier COA on inbound lot follows through to WWI/relabel lot
            try:
                from .coa_supplier import clone_lot_coa_certificate

                if src_lot:
                    clone_lot_coa_certificate(src_lot, new_lot, user=user)
            except Exception:
                logger.exception(
                    "Failed to clone supplier COA onto relabel lot %s (batch %s)",
                    lot_number,
                    batch.batch_number,
                )
        else:
            new_lot = Lot.objects.create(
                lot_number=lot_number,
                item=item,
                pack_size=pack_size,
                quantity=output_quantity,
                quantity_remaining=output_quantity,
                quantity_on_hold=output_quantity,
                received_date=closed_dt,
                manufacture_date=closed_dt,
                expiration_date=output_expiration,
                status="on_hold",
                on_hold=True,
            )
            _copy_inbound_traceability(new_lot, src_lot)

        ProductionBatchOutput.objects.create(
            batch=batch,
            lot=new_lot,
            quantity_produced=output_quantity,
        )

        if not is_relabel:
            try:
                from .hold_services import ensure_open_hold_case, parse_batch_qc_notes, parse_qc_float

                qc_param = (data.get("qc_parameter") or data.get("qc_parameters") or "").strip()
                qc_actual = data.get("qc_actual")
                qc_initials = (data.get("qc_initials") or "").strip()
                if not qc_param and not qc_actual and not qc_initials:
                    parsed = parse_batch_qc_notes(batch.notes)
                    qc_param = parsed["parameter"]
                    qc_actual = parsed["actual_value"]
                    qc_initials = parsed["initials"]
                qc_val = parse_qc_float(qc_actual)
                summary = "Awaiting micro/QC results"
                if qc_param and qc_val is not None:
                    summary = f"Awaiting micro/QC — {qc_param}: {qc_val:g}"
                elif qc_param:
                    summary = f"Awaiting micro/QC — {qc_param}"

                ensure_open_hold_case(
                    new_lot,
                    user=user,
                    kind="awaiting_micro",
                    summary=summary,
                    initial_note=(
                        f"Repack lot from batch {batch.batch_number} "
                        "placed on hold pending micro/QC release."
                    ),
                    qc_parameter_name=qc_param,
                    qc_result_value=qc_val,
                    qc_initials=qc_initials,
                )
            except Exception:
                logger.exception(
                    "Failed to open awaiting_micro hold case for lot %s (batch %s)",
                    new_lot.lot_number,
                    batch.batch_number,
                )

        _uom = getattr(item, "unit_of_measure", None) or "lbs"
        doc_bits = []
        if (batch.wastes or 0) > 0:
            doc_bits.append(f"wastes {batch.wastes} {_uom} documented")
        if (batch.spills or 0) > 0:
            doc_bits.append(f"spills {batch.spills} {_uom} documented")
        doc_suffix = f" — {', '.join(doc_bits)}" if doc_bits else ""
        txn = InventoryTransaction.objects.create(
            transaction_type="repack_output",
            lot=new_lot,
            quantity=output_quantity,
            notes=(
                f"Repack batch {batch.batch_number} output "
                f"({output_quantity} {_uom} produced{doc_suffix})"
            ),
            reference_number=batch.batch_number,
        )
        log_lot_transaction(
            lot=new_lot,
            quantity_before=0.0,
            quantity_change=output_quantity,
            transaction_type="repack_output",
            reference_number=batch.batch_number,
            reference_type="batch_number",
            transaction_id=txn.id,
            batch_id=batch.id,
            notes=(
                f"Repack batch {batch.batch_number} output - "
                "Distributed item relabeled/repacked"
            ),
        )

    return batch


def reverse_batch_ticket(batch: ProductionBatch) -> dict:
    """Reverse (unclose/delete) a batch ticket. Returns a small info dict."""
    from .reversal_guard import build_batch_reversal_plan, get_production_batch_reversal_blockers
    from .views import log_lot_transaction

    blockers = get_production_batch_reversal_blockers(batch)
    if blockers:
        raise MakeFlowError(
            "Cannot reverse this batch until dependencies are cleared.",
            extra={
                "blockers": blockers,
                "reversal_plan": build_batch_reversal_plan(batch),
            },
        )

    batch_number = batch.batch_number
    batch_id = batch.id

    try:
        input_materials = []
        input_lots = []
        for input_item in batch.inputs.all():
            try:
                input_materials.append(
                    {
                        "item_sku": input_item.lot.item.sku,
                        "item_name": input_item.lot.item.name,
                        "quantity_used": input_item.quantity_used,
                    }
                )
                input_lots.append(input_item.lot.lot_number)
            except Exception:
                pass

        output_lot_number = None
        output_quantity = None
        output = batch.outputs.first()
        if output:
            try:
                output_lot_number = output.lot.lot_number
                output_quantity = output.quantity_produced
            except Exception:
                pass

        ProductionLog.objects.create(
            batch=batch,
            batch_number=batch.batch_number,
            batch_type=batch.batch_type,
            finished_good_sku=batch.finished_good_item.sku,
            finished_good_name=batch.finished_good_item.name,
            quantity_produced=batch.quantity_produced,
            quantity_actual=batch.quantity_actual,
            variance=batch.variance,
            wastes=batch.wastes,
            spills=batch.spills,
            production_date=batch.production_date,
            closed_date=batch.closed_date or timezone.now(),
            input_materials=json.dumps(input_materials),
            input_lots=json.dumps(input_lots),
            output_lot_number=output_lot_number,
            output_quantity=output_quantity,
            notes=f"BATCH UNCLOSED/REVERSED - {batch.notes or ''}",
            recipe_snapshot=getattr(batch, "recipe_snapshot", None) or None,
            closed_by=None,
            logged_at=timezone.now(),
        )
    except Exception as log_error:
        logger.warning(
            "Failed to create unclose log entry for batch %s: %s",
            batch_number,
            log_error,
        )

    output_lot_ids = []
    output_lots_to_delete = []
    try:
        for batch_output in batch.outputs.all():
            lot_id = batch_output.lot_id
            if lot_id:
                output_lot_ids.append(lot_id)
                try:
                    lot = Lot.objects.get(id=lot_id)
                    output_lots_to_delete.append(lot)
                except Lot.DoesNotExist:
                    pass
    except Exception:
        pass

    input_lot_ids = list(batch.inputs.values_list("lot_id", flat=True))

    if batch.status == "closed":
        for batch_input in batch.inputs.all():
            try:
                lot_id = batch_input.lot_id
                if lot_id:
                    lot = Lot.objects.get(id=lot_id)
                    lot.quantity_remaining = round(
                        lot.quantity_remaining + batch_input.quantity_used, 2
                    )
                    lot.save()
            except (Lot.DoesNotExist, AttributeError, ValueError):
                pass

    if output_lot_ids:
        InventoryTransaction.objects.filter(lot_id__in=output_lot_ids).delete()

    for lot in output_lots_to_delete:
        try:
            lot.delete()
        except Exception:
            pass

    if input_lot_ids:
        transactions = InventoryTransaction.objects.filter(
            lot_id__in=input_lot_ids,
            reference_number=batch_number,
            transaction_type__in=["production_input", "repack_input"],
        )
        for txn in transactions:
            try:
                lot_id = txn.lot_id
                if not lot_id:
                    continue
                try:
                    lot = Lot.objects.get(id=lot_id)
                    reverse_quantity = abs(txn.quantity)
                    reverse_transaction = InventoryTransaction.objects.create(
                        transaction_type="adjustment",
                        lot=lot,
                        quantity=reverse_quantity,
                        reference_number=batch_number,
                        notes=f"UNFK: Reverse batch {batch_number} - Return input to inventory",
                    )
                    log_lot_transaction(
                        lot=lot,
                        quantity_before=lot.quantity_remaining - reverse_quantity,
                        quantity_change=reverse_quantity,
                        transaction_type="adjustment",
                        reference_number=batch_number,
                        reference_type="batch_number",
                        transaction_id=reverse_transaction.id,
                        batch_id=batch_id,
                        notes=f"UNFK: Reversed batch {batch_number} - Input returned to inventory",
                    )
                except Lot.DoesNotExist:
                    pass
            except (AttributeError, ValueError, TypeError) as e:
                logger.exception("Error processing transaction %s: %s", txn.id, e)

    batch.delete()

    return {
        "message": "Batch ticket reversed successfully",
        "batch_number": batch_number,
    }
