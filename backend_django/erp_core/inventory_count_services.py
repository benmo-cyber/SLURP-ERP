"""
Physical inventory / beginning-balance count sessions.

Lot-level count → variance report → qty-only post (audit via LotTransactionLog).
No GL posting in v1.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from .lot_services import LotFlowError, reconcile_lot
from .models import InventoryCountLine, InventoryCountSession, InventoryTransaction, Item, Lot

logger = logging.getLogger(__name__)


class InventoryCountError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _username(user) -> str:
    return (
        getattr(user, "username", None)
        or getattr(user, "email", None)
        or "system"
    )


def _require_staff(user) -> None:
    if not getattr(user, "is_authenticated", True) or (
        not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False)
    ):
        raise InventoryCountError("Inventory count requires staff or superuser.", status_code=403)


def _next_session_number(count_date: date) -> str:
    prefix = f"IC-{count_date.strftime('%Y%m%d')}-"
    existing = (
        InventoryCountSession.objects.filter(session_number__startswith=prefix)
        .order_by("-session_number")
        .values_list("session_number", flat=True)
        .first()
    )
    seq = 1
    if existing:
        try:
            seq = int(str(existing).rsplit("-", 1)[-1]) + 1
        except (TypeError, ValueError):
            seq = InventoryCountSession.objects.filter(session_number__startswith=prefix).count() + 1
    return f"{prefix}{seq:03d}"


def _lot_is_on_hold(lot: Lot) -> bool:
    if not lot:
        return False
    if (lot.status or "") == "on_hold" or bool(lot.on_hold):
        return True
    return float(getattr(lot, "quantity_on_hold", 0) or 0) > 0.0001


def _lot_on_hold_qty(lot: Lot) -> float:
    if not lot:
        return 0.0
    qoh = float(getattr(lot, "quantity_on_hold", 0) or 0)
    if qoh > 0:
        return qoh
    if (lot.status or "") == "on_hold" or bool(lot.on_hold):
        return float(lot.quantity_remaining or 0)
    return 0.0


def _open_lot_queryset():
    return (
        Lot.objects.select_related("item")
        .filter(quantity_remaining__gt=0)
        .exclude(status="rejected")
        .order_by("item__sku", "lot_number")
    )


def _line_from_lot(session: InventoryCountSession, lot: Lot) -> InventoryCountLine:
    item = lot.item
    return InventoryCountLine(
        session=session,
        lot=lot,
        item=item,
        lot_number_snapshot=lot.lot_number or "",
        sku_snapshot=item.sku or "",
        item_name_snapshot=item.name or "",
        vendor_snapshot=item.vendor or "",
        unit_of_measure=(item.unit_of_measure or "lbs"),
        system_qty=float(lot.quantity_remaining or 0),
        counted_qty=None,
        is_new_lot=False,
        on_hold_snapshot=_lot_is_on_hold(lot),
        on_hold_qty_snapshot=_lot_on_hold_qty(lot),
    )


@transaction.atomic
def create_count_session(
    user,
    *,
    count_type: str,
    count_date: date | str | None = None,
    name: str = "",
    notes: str = "",
    snapshot_open_lots: bool | None = None,
) -> InventoryCountSession:
    """
    Start a count session.

    annual_physical / ad_hoc: snapshot all open lots by default.
    beginning_balance: empty sheet by default (add lots / create on post).
    """
    _require_staff(user)
    if count_type not in dict(InventoryCountSession.COUNT_TYPE_CHOICES):
        raise InventoryCountError("Invalid count type.")

    open_existing = InventoryCountSession.objects.filter(
        status__in=("draft", "review")
    ).exists()
    if open_existing:
        raise InventoryCountError(
            "Another inventory count is already open. Finish or cancel it before starting a new one."
        )

    if isinstance(count_date, str):
        count_date = date.fromisoformat(count_date) if count_date.strip() else timezone.localdate()
    count_date = count_date or timezone.localdate()

    if snapshot_open_lots is None:
        snapshot_open_lots = count_type != "beginning_balance"

    session = InventoryCountSession.objects.create(
        session_number=_next_session_number(count_date),
        count_type=count_type,
        status="draft",
        count_date=count_date,
        name=(name or "").strip()
        or dict(InventoryCountSession.COUNT_TYPE_CHOICES).get(count_type, "Count"),
        notes=(notes or "").strip(),
        created_by=_username(user),
    )

    if snapshot_open_lots:
        lines = [_line_from_lot(session, lot) for lot in _open_lot_queryset()]
        if lines:
            InventoryCountLine.objects.bulk_create(lines, batch_size=500)

    return session


@transaction.atomic
def refresh_snapshot_missing_lots(session: InventoryCountSession) -> int:
    """Add any open lots not already on the session (draft only)."""
    if session.status != "draft":
        raise InventoryCountError("Cannot refresh a count that is not in draft.")
    existing_lot_ids = set(
        session.lines.exclude(lot_id=None).values_list("lot_id", flat=True)
    )
    to_add = []
    for lot in _open_lot_queryset():
        if lot.id in existing_lot_ids:
            continue
        to_add.append(_line_from_lot(session, lot))
    if to_add:
        InventoryCountLine.objects.bulk_create(to_add, batch_size=500)
    return len(to_add)


def update_count_line(
    user,
    line: InventoryCountLine,
    *,
    counted_qty: float | str | None,
    include_in_post: bool | None = None,
    line_notes: str | None = None,
    vendor_lot_number: str | None = None,
) -> InventoryCountLine:
    _require_staff(user)
    session = line.session
    if not session.is_editable:
        raise InventoryCountError("This count is locked.")

    if counted_qty is not None and str(counted_qty).strip() != "":
        try:
            qty = round(float(counted_qty), 4)
        except (TypeError, ValueError) as e:
            raise InventoryCountError("Counted quantity must be a number.") from e
        if qty < 0:
            raise InventoryCountError("Counted quantity cannot be negative.")
        line.counted_qty = qty
    else:
        line.counted_qty = None

    if include_in_post is not None:
        line.include_in_post = bool(include_in_post)
    if line_notes is not None:
        line.line_notes = (line_notes or "").strip()[:500]
    if vendor_lot_number is not None and line.is_new_lot:
        line.vendor_lot_number = (vendor_lot_number or "").strip()[:100]

    line.save()
    return line


def bulk_update_counted_qtys(user, session: InventoryCountSession, updates: dict[int, Any]) -> int:
    """updates: {line_id: counted_qty_str_or_number}"""
    _require_staff(user)
    if not session.is_editable:
        raise InventoryCountError("This count is locked.")
    updated = 0
    lines = {ln.id: ln for ln in session.lines.filter(id__in=list(updates.keys()))}
    for line_id, raw in updates.items():
        line = lines.get(int(line_id))
        if not line:
            continue
        update_count_line(user, line, counted_qty=raw)
        updated += 1
    return updated


@transaction.atomic
def add_new_lot_line(
    user,
    session: InventoryCountSession,
    *,
    item_id: int,
    counted_qty: float | str,
    vendor_lot_number: str = "",
    manufacture_date: date | str | None = None,
    expiration_date: date | str | None = None,
    line_notes: str = "",
) -> InventoryCountLine:
    """Found stock / beginning balance row — creates a Lot on post."""
    _require_staff(user)
    if not session.is_editable:
        raise InventoryCountError("This count is locked.")
    try:
        item = Item.objects.get(pk=int(item_id))
    except (Item.DoesNotExist, TypeError, ValueError) as e:
        raise InventoryCountError("Select a valid item.") from e
    try:
        qty = round(float(counted_qty), 4)
    except (TypeError, ValueError) as e:
        raise InventoryCountError("Counted quantity must be a number.") from e
    if qty < 0:
        raise InventoryCountError("Counted quantity cannot be negative.")

    def _parse_d(v):
        if v is None or v == "":
            return None
        if isinstance(v, date) and not isinstance(v, datetime):
            return v
        return date.fromisoformat(str(v)[:10])

    return InventoryCountLine.objects.create(
        session=session,
        lot=None,
        item=item,
        lot_number_snapshot="",
        sku_snapshot=item.sku or "",
        item_name_snapshot=item.name or "",
        vendor_snapshot=item.vendor or "",
        unit_of_measure=(item.unit_of_measure or "lbs"),
        system_qty=0.0,
        counted_qty=qty,
        is_new_lot=True,
        vendor_lot_number=(vendor_lot_number or "").strip()[:100],
        manufacture_date=_parse_d(manufacture_date),
        expiration_date=_parse_d(expiration_date),
        line_notes=(line_notes or "").strip()[:500],
    )


def mark_session_review(user, session: InventoryCountSession) -> InventoryCountSession:
    _require_staff(user)
    if session.status not in ("draft", "review"):
        raise InventoryCountError("Only an open count can enter variance review.")
    missing = session.lines.filter(counted_qty__isnull=True, include_in_post=True).count()
    if missing:
        raise InventoryCountError(
            f"{missing} line(s) still need a counted quantity (or uncheck Include before review)."
        )
    session.status = "review"
    session.reviewed_at = timezone.now()
    session.reviewed_by = _username(user)
    session.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])
    return session


def reopen_session_draft(user, session: InventoryCountSession) -> InventoryCountSession:
    _require_staff(user)
    if session.status != "review":
        raise InventoryCountError("Only a review session can be reopened for counting.")
    session.status = "draft"
    session.save(update_fields=["status", "updated_at"])
    return session


def variance_summary(session: InventoryCountSession) -> dict:
    lines = list(session.lines.select_related("item", "lot").all())
    counted = [ln for ln in lines if ln.counted_qty is not None]
    variance_lines = [ln for ln in counted if abs(float(ln.variance or 0)) > 0.0001]
    uncounted = [ln for ln in lines if ln.counted_qty is None]
    in_progress = [ln for ln in lines if ln.progress_status == "in_progress"]
    not_started = [ln for ln in lines if ln.progress_status == "not_started"]
    line_count = len(lines)
    counted_count = len(counted)
    if line_count == 0:
        progress_status = "not_started"
    elif counted_count >= line_count:
        progress_status = "complete"
    elif counted_count > 0 or in_progress:
        progress_status = "in_progress"
    else:
        progress_status = "not_started"
    pct = int(round(100.0 * counted_count / line_count)) if line_count else 0
    return {
        "line_count": line_count,
        "counted_count": counted_count,
        "uncounted_count": len(uncounted),
        "in_progress_count": len(in_progress),
        "not_started_count": len(not_started),
        "variance_count": len(variance_lines),
        "zero_variance_count": len(counted) - len(variance_lines),
        "new_lot_count": sum(1 for ln in lines if ln.is_new_lot),
        "absolute_variance_qty": sum(abs(float(ln.variance or 0)) for ln in variance_lines),
        "net_variance_qty": sum(float(ln.variance or 0) for ln in variance_lines),
        "progress_pct": pct,
        "progress_status": progress_status,
        "lines": lines,
        "variance_lines": variance_lines,
        "uncounted_lines": uncounted,
    }


def _create_lot_from_line(user, session: InventoryCountSession, line: InventoryCountLine) -> Lot:
    from .views import generate_lot_number

    qty = float(line.counted_qty or 0)
    received = timezone.make_aware(
        datetime.combine(session.count_date, datetime.min.time())
    )
    mfg = None
    exp = None
    if line.manufacture_date:
        mfg = timezone.make_aware(datetime.combine(line.manufacture_date, datetime.min.time()))
    if line.expiration_date:
        exp = timezone.make_aware(datetime.combine(line.expiration_date, datetime.min.time()))

    lot = Lot.objects.create(
        lot_number=generate_lot_number(),
        vendor_lot_number=line.vendor_lot_number or None,
        item=line.item,
        quantity=qty,
        quantity_remaining=qty,
        received_date=received,
        manufacture_date=mfg,
        expiration_date=exp,
        status="accepted",
        on_hold=False,
        quantity_on_hold=0.0,
        short_reason=None,
        po_number=None,
    )
    InventoryTransaction.objects.create(
        transaction_type="adjustment",
        lot=lot,
        quantity=qty,
        reference_number=session.session_number,
        notes=f"Created from inventory count {session.session_number}",
    )
    try:
        from .models import LotTransactionLog

        LotTransactionLog.objects.create(
            lot=lot,
            lot_number=lot.lot_number or "",
            item_sku=lot.item.sku,
            item_name=lot.item.name,
            vendor=lot.item.vendor or "",
            transaction_type="adjustment",
            quantity_before=0.0,
            quantity_change=qty,
            quantity_after=qty,
            unit_of_measure=lot.item.unit_of_measure,
            reference_number=session.session_number,
            reference_type="inventory_count",
            notes=(line.line_notes or f"Beginning balance / found lot from {session.session_number}"),
            logged_by=_username(user),
        )
    except Exception as e:
        logger.warning("Failed to log new count lot: %s", e)
    return lot


@transaction.atomic
def post_count_session(user, session: InventoryCountSession) -> InventoryCountSession:
    """
    Apply counted quantities: reconcile existing lots; create lots for new/found lines.
    Qty + audit only (no GL).
    """
    _require_staff(user)
    if session.status not in ("draft", "review"):
        raise InventoryCountError("This count is already posted or cancelled.")

    lines = list(
        session.lines.select_related("lot", "item").filter(include_in_post=True, posted=False)
    )
    missing = [ln for ln in lines if ln.counted_qty is None]
    if missing:
        raise InventoryCountError(
            f"Cannot post: {len(missing)} included line(s) still lack a counted quantity."
        )

    reason_base = f"Inventory count {session.session_number}"
    for line in lines:
        variance = float(line.counted_qty) - float(line.system_qty or 0)
        if line.is_new_lot or line.lot_id is None:
            if float(line.counted_qty) <= 0:
                # Creating a zero lot is useless; skip create but mark posted
                line.posted = True
                line.posted_variance = variance
                line.save(update_fields=["posted", "posted_variance"])
                continue
            lot = _create_lot_from_line(user, session, line)
            line.created_lot = lot
            line.lot = lot
            line.lot_number_snapshot = lot.lot_number or ""
            line.posted = True
            line.posted_variance = variance
            line.save(
                update_fields=[
                    "created_lot",
                    "lot",
                    "lot_number_snapshot",
                    "posted",
                    "posted_variance",
                ]
            )
            continue

        lot = line.lot
        if lot is None:
            raise InventoryCountError(f"Line {line.id} missing lot.")
        try:
            reconcile_lot(
                user,
                lot,
                float(line.counted_qty),
                reason=f"{reason_base}: {line.line_notes}".strip(": "),
            )
        except LotFlowError as e:
            raise InventoryCountError(e.message, status_code=e.status_code) from e

        # Enrich latest log reference when possible
        try:
            from .models import LotTransactionLog

            log = (
                LotTransactionLog.objects.filter(lot=lot, reference_type="admin_reconcile")
                .order_by("-id")
                .first()
            )
            if log and (not log.reference_number or log.reference_type == "admin_reconcile"):
                log.reference_number = session.session_number
                log.reference_type = "inventory_count"
                log.save(update_fields=["reference_number", "reference_type"])
        except Exception:
            pass

        line.posted = True
        line.posted_variance = variance
        line.save(update_fields=["posted", "posted_variance"])

    session.status = "posted"
    session.posted_at = timezone.now()
    session.posted_by = _username(user)
    session.save(update_fields=["status", "posted_at", "posted_by", "updated_at"])
    return session


@transaction.atomic
def cancel_count_session(user, session: InventoryCountSession) -> InventoryCountSession:
    _require_staff(user)
    if session.status == "posted":
        raise InventoryCountError("Cannot cancel a posted count.")
    if session.status == "cancelled":
        return session
    session.status = "cancelled"
    session.save(update_fields=["status", "updated_at"])
    return session
