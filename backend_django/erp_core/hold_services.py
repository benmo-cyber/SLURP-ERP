"""
Hold investigation cases: notes/photos + resolve (accept / return / discard).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .lot_services import LotFlowError, release_from_hold
from .models import InventoryTransaction, Lot, LotHoldCase, LotHoldNote

logger = logging.getLogger(__name__)


def _actor(user) -> str:
    return getattr(user, "username", None) or getattr(user, "email", None) or "system"


def open_hold_qty(lot: Lot) -> float:
    return float(getattr(lot, "quantity_on_hold", 0) or 0)


def parse_qc_float(raw) -> float | None:
    """Parse measured QC values like '0.71', '.7', '0,71'."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_batch_qc_notes(notes: str | None) -> dict:
    """Extract QC Parameters / Actual / Initials lines from batch close notes."""
    text = notes or ""
    out = {"parameter": "", "actual": "", "actual_value": None, "initials": ""}
    if not text:
        return out
    m = re.search(r"QC Parameters:\s*(.+?)(?:\n|QC Actual:|$)", text, re.IGNORECASE | re.DOTALL)
    if m:
        out["parameter"] = m.group(1).strip()
    m = re.search(r"QC Actual:\s*(.+?)(?:\n|QC Initials:|$)", text, re.IGNORECASE | re.DOTALL)
    if m:
        out["actual"] = m.group(1).strip()
        out["actual_value"] = parse_qc_float(out["actual"])
    m = re.search(r"QC Initials:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if m:
        out["initials"] = m.group(1).strip()[:40]
    return out


def qc_prefill_for_hold_case(case: LotHoldCase) -> dict:
    """
    QC values to show on the hold-case COA/micro form.

    Prefer values stored on the case (ported at batch close); else parse the
    linked production batch notes.
    """
    param = (getattr(case, "qc_parameter_name", None) or "").strip()
    val = getattr(case, "qc_result_value", None)
    initials = (getattr(case, "qc_initials", None) or "").strip()
    if val is None or not param:
        from .models import ProductionBatchOutput

        out = (
            ProductionBatchOutput.objects.filter(lot_id=case.lot_id)
            .select_related("batch")
            .order_by("-id")
            .first()
        )
        if out and out.batch_id:
            parsed = parse_batch_qc_notes(out.batch.notes)
            if not param:
                param = parsed["parameter"]
            if val is None:
                val = parsed["actual_value"]
            if not initials:
                initials = parsed["initials"]
            # Persist onto open case so later views / resolves see it.
            if case.status == "open" and (param or val is not None or initials):
                dirty = []
                if param and not (case.qc_parameter_name or "").strip():
                    case.qc_parameter_name = param[:255]
                    dirty.append("qc_parameter_name")
                if val is not None and case.qc_result_value is None:
                    case.qc_result_value = val
                    dirty.append("qc_result_value")
                if initials and not (case.qc_initials or "").strip():
                    case.qc_initials = initials[:40]
                    dirty.append("qc_initials")
                if dirty:
                    case.save(update_fields=dirty)
    return {
        "qc_parameter_name": param,
        "qc_result_value": val,
        "qc_initials": initials,
    }


def ensure_open_hold_case(
    lot: Lot,
    *,
    user=None,
    summary: str = "",
    initial_note: str = "",
    kind: str = "receiving",
    qc_parameter_name: str = "",
    qc_result_value=None,
    qc_initials: str = "",
) -> LotHoldCase:
    """Get or create the open hold case for a lot; optionally append an opening note."""
    kind = (kind or "receiving").strip().lower()
    if kind not in ("receiving", "awaiting_micro", "customer_return"):
        kind = "receiving"

    qc_name = (qc_parameter_name or "").strip()[:255]
    qc_val = parse_qc_float(qc_result_value)
    qc_init = (qc_initials or "").strip()[:40]

    case = (
        LotHoldCase.objects.filter(lot=lot, status="open")
        .order_by("-opened_at")
        .first()
    )
    if case is None:
        case = LotHoldCase.objects.create(
            lot=lot,
            status="open",
            kind=kind,
            summary=(summary or "").strip()[:255],
            opened_by=_actor(user),
            qc_parameter_name=qc_name,
            qc_result_value=qc_val,
            qc_initials=qc_init,
        )
    else:
        update_fields = []
        if summary and not (case.summary or "").strip():
            case.summary = summary.strip()[:255]
            update_fields.append("summary")
        # Upgrade receiving → awaiting_micro if batch close opens micro hold on same lot.
        if kind == "awaiting_micro" and (case.kind or "") != "awaiting_micro":
            case.kind = "awaiting_micro"
            update_fields.append("kind")
        if qc_name and not (case.qc_parameter_name or "").strip():
            case.qc_parameter_name = qc_name
            update_fields.append("qc_parameter_name")
        if qc_val is not None and case.qc_result_value is None:
            case.qc_result_value = qc_val
            update_fields.append("qc_result_value")
        if qc_init and not (case.qc_initials or "").strip():
            case.qc_initials = qc_init
            update_fields.append("qc_initials")
        if update_fields:
            case.save(update_fields=update_fields)

    note_body = (initial_note or "").strip()
    if qc_name or qc_val is not None or qc_init:
        qc_lines = ["Batch-close QC ported to this hold case:"]
        if qc_name:
            qc_lines.append(f"  Parameter: {qc_name}")
        if qc_val is not None:
            qc_lines.append(f"  Result: {qc_val:g}")
        if qc_init:
            qc_lines.append(f"  Initials: {qc_init}")
        qc_block = "\n".join(qc_lines)
        note_body = f"{note_body}\n\n{qc_block}".strip() if note_body else qc_block

    if note_body:
        LotHoldNote.objects.create(
            case=case,
            body=note_body,
            created_by=_actor(user),
        )
    return case


def add_hold_note(
    case: LotHoldCase,
    *,
    user=None,
    body: str = "",
    photo=None,
) -> LotHoldNote:
    if case.status != "open":
        raise LotFlowError("Cannot add notes to a resolved hold case.")
    text = (body or "").strip()
    if not text and not photo:
        raise LotFlowError("Enter a note and/or attach a photo.")
    return LotHoldNote.objects.create(
        case=case,
        body=text,
        photo=photo,
        created_by=_actor(user),
    )


def _remove_held_quantity(lot: Lot, qty: float, *, txn_notes: str, user) -> Lot:
    """Drop qty from both on-hold and on-hand (return / discard)."""
    from .views import log_lot_transaction

    qty = round(float(qty), 2)
    if qty <= 0:
        raise LotFlowError("Quantity must be positive.")
    hold = open_hold_qty(lot)
    if qty > hold + 1e-6:
        raise LotFlowError(f"Only {hold} on hold; cannot remove more than that.")
    remaining = float(lot.quantity_remaining or 0)
    if qty > remaining + 1e-6:
        raise LotFlowError(f"Only {remaining} remaining on lot; cannot remove more.")

    quantity_before = remaining
    new_hold = round(hold - qty, 2)
    new_remaining = round(remaining - qty, 2)
    if new_hold <= 0:
        new_hold = 0.0

    lot.quantity_on_hold = new_hold
    lot.quantity_remaining = max(0.0, new_remaining)
    if new_hold <= 0:
        lot.on_hold = False
        lot.status = "accepted" if lot.quantity_remaining > 0 else "rejected"
    else:
        lot.on_hold = True
        lot.status = "on_hold"
    lot.save(
        update_fields=[
            "quantity_on_hold",
            "quantity_remaining",
            "on_hold",
            "status",
            "depleted_at",
        ]
    )

    txn = InventoryTransaction.objects.create(
        transaction_type="adjustment",
        lot=lot,
        quantity=round(-qty, 2),
        notes=txn_notes,
    )
    log_lot_transaction(
        lot=lot,
        quantity_before=quantity_before,
        quantity_change=-qty,
        transaction_type="adjustment",
        reference_type="hold_resolution",
        transaction_id=txn.id,
        notes=txn_notes,
    )
    return lot


def resolve_hold_case(
    case: LotHoldCase,
    *,
    user,
    resolution: str,
    quantity: float,
    notes: str = "",
    coa_payload: dict | None = None,
) -> LotHoldCase:
    """
    Close (or partially resolve) a hold case.
    - accept: release_from_hold (available inventory)
    - return / discard: remove from hold and from on-hand
    If qty < full hold and hold remains, case stays open with a resolution note.
    """
    resolution = (resolution or "").strip().lower()
    if resolution not in ("accept", "return", "discard"):
        raise LotFlowError("Choose accept, return, or discard.")
    if case.status != "open":
        raise LotFlowError("This hold case is already resolved.")

    lot = Lot.objects.select_related("item", "source_lot").get(pk=case.lot_id)
    try:
        qty = round(float(quantity), 2)
    except (TypeError, ValueError) as e:
        raise LotFlowError("Valid quantity is required.") from e
    if qty <= 0:
        raise LotFlowError("Quantity must be positive.")

    hold = open_hold_qty(lot)
    if hold <= 0:
        raise LotFlowError("Lot has no quantity on hold.")
    if qty > hold + 1e-6:
        raise LotFlowError(f"Only {hold} on hold.")

    note_prefix = {
        "accept": "Accepted after investigation",
        "return": "Returned to vendor",
        "discard": "Discarded / scrapped",
    }[resolution]
    if resolution == "accept" and (case.kind or "") == "customer_return":
        src_label = (
            lot.source_lot.lot_number
            if lot.source_lot_id
            else str(lot.source_lot_id)
        )
        note_body = (
            f"Accepted after RMA investigation — merged {qty} "
            f"{(lot.item.unit_of_measure or '').strip()} into source lot {src_label}."
        )
        if (notes or "").strip():
            note_body = f"{note_body}\n{(notes or '').strip()}"
    else:
        note_body = f"{note_prefix}: {qty} {(lot.item.unit_of_measure or '').strip()}."
        if (notes or "").strip():
            note_body = f"{note_body}\n{(notes or '').strip()}"

    with transaction.atomic():
        if resolution == "accept":
            if (case.kind or "") == "customer_return" and getattr(
                lot, "source_lot_id", None
            ):
                from .rma_services import merge_rma_staging_into_source
                from .sell_services import SellFlowError as _SellFlowError

                try:
                    merge_rma_staging_into_source(
                        lot, qty=qty, user=user, notes=notes or ""
                    )
                except _SellFlowError as e:
                    raise LotFlowError(e.message) from e
            else:
                release_from_hold(user, lot, qty, coa_payload=coa_payload)
        else:
            label = "Return to vendor" if resolution == "return" else "Discard from hold"
            _remove_held_quantity(
                lot,
                qty,
                txn_notes=f"{label} — case {case.pk}",
                user=user,
            )

        LotHoldNote.objects.create(
            case=case,
            body=note_body,
            created_by=_actor(user),
        )

        lot.refresh_from_db()
        still_held = open_hold_qty(lot) > 0.0001
        if still_held:
            # Partial resolution — leave case open for remaining hold.
            case.resolution = resolution
            case.resolution_qty = qty
            case.resolution_notes = (notes or "").strip()
            case.save(update_fields=["resolution", "resolution_qty", "resolution_notes"])
        else:
            case.status = "resolved"
            case.resolution = resolution
            case.resolution_qty = qty
            case.resolution_notes = (notes or "").strip()
            case.resolved_at = timezone.now()
            case.resolved_by = _actor(user)
            case.save(
                update_fields=[
                    "status",
                    "resolution",
                    "resolution_qty",
                    "resolution_notes",
                    "resolved_at",
                    "resolved_by",
                ]
            )
            # Close RMA when all staging for its lines is resolved and fully received.
            if (case.kind or "") == "customer_return" and lot.rma_number:
                from .models import CustomerRma
                from .rma_services import refresh_rma_receive_status

                rma = (
                    CustomerRma.objects.filter(rma_number=lot.rma_number)
                    .exclude(status="cancelled")
                    .first()
                )
                if rma is not None:
                    refresh_rma_receive_status(rma)
                    rma.refresh_from_db()
                    if rma.status == "received":
                        # Any open customer_return holds still open for this RMA?
                        open_holds = LotHoldCase.objects.filter(
                            lot__rma_number=rma.rma_number,
                            kind="customer_return",
                            status="open",
                        ).exists()
                        if not open_holds:
                            rma.status = "closed"
                            rma.closed_at = timezone.now()
                            rma.save(update_fields=["status", "closed_at", "updated_at"])
    return case
