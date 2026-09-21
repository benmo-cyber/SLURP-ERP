"""
Hold investigation cases: notes/photos + resolve (accept / return / discard).
"""
from __future__ import annotations

import logging
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


def ensure_open_hold_case(
    lot: Lot,
    *,
    user=None,
    summary: str = "",
    initial_note: str = "",
) -> LotHoldCase:
    """Get or create the open hold case for a lot; optionally append an opening note."""
    case = (
        LotHoldCase.objects.filter(lot=lot, status="open")
        .order_by("-opened_at")
        .first()
    )
    if case is None:
        case = LotHoldCase.objects.create(
            lot=lot,
            status="open",
            summary=(summary or "").strip()[:255],
            opened_by=_actor(user),
        )
    elif summary and not (case.summary or "").strip():
        case.summary = summary.strip()[:255]
        case.save(update_fields=["summary"])

    note_body = (initial_note or "").strip()
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

    lot = Lot.objects.select_related("item").get(pk=case.lot_id)
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
    note_body = f"{note_prefix}: {qty} {(lot.item.unit_of_measure or '').strip()}."
    if (notes or "").strip():
        note_body = f"{note_body}\n{(notes or '').strip()}"

    with transaction.atomic():
        if resolution == "accept":
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
    return case
