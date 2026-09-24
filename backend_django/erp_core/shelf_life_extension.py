"""Shelf life extension: re-QC date + months → new lot expiration + master COA refresh."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone


class ShelfLifeExtensionError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _add_months(d: date, months: int) -> date:
    """Add calendar months (clamp day to last day of target month)."""
    if months < 0:
        raise ValueError("months must be non-negative")
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last = monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _as_aware_midnight(d: date):
    dt = datetime.combine(d, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def _date_iso(dt) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "date") and not isinstance(dt, date):
        local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
        return local.date().isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)


@transaction.atomic
def extend_lot_shelf_life(
    user,
    lot,
    *,
    qc_date: date,
    extension_months: int,
    qc_result_value: Optional[float] = None,
    notes: str = "",
) -> Any:
    """
    Set lot.expiration_date = qc_date + extension_months.
    Refresh master COA (keep micro line results); optional new QC result.
    Returns LotShelfLifeExtension.
    """
    from .coa_logic import evaluate_qc_numeric_pass
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .formula_resolve import formula_for_lot
    from .models import (
        LotAttributeChangeLog,
        LotCoaCertificate,
        LotShelfLifeExtension,
    )

    if lot is None:
        raise ShelfLifeExtensionError("Lot is required.")
    item = getattr(lot, "item", None)
    if item is None or getattr(item, "item_type", "") not in (
        "finished_good",
        "distributed_item",
    ):
        raise ShelfLifeExtensionError(
            "Shelf life extension applies to finished goods / distributed items only."
        )
    try:
        months = int(extension_months)
    except (TypeError, ValueError):
        raise ShelfLifeExtensionError("Extension months must be a whole number.")
    if months < 1:
        raise ShelfLifeExtensionError("Extension months must be at least 1.")
    if not isinstance(qc_date, date):
        raise ShelfLifeExtensionError("QC date is required.")

    rem = float(getattr(lot, "quantity_remaining", 0) or 0)
    if rem <= 0:
        raise ShelfLifeExtensionError("Lot has no remaining quantity.")

    new_exp_date = _add_months(qc_date, months)
    new_exp = _as_aware_midnight(new_exp_date)
    old_exp = lot.expiration_date
    who = getattr(user, "username", None) or getattr(user, "get_username", lambda: "")() or ""

    formula = formula_for_lot(lot)
    qname = ""
    qmin = qmax = None
    if formula is not None:
        qname = (formula.qc_parameter_name or "").strip()
        qmin = formula.qc_spec_min
        qmax = formula.qc_spec_max

    qc_pass = None
    if qc_result_value is not None and qname:
        qc_pass = evaluate_qc_numeric_pass(qc_result_value, qmin, qmax)

    lot.expiration_date = new_exp
    lot.save(update_fields=["expiration_date"])

    LotAttributeChangeLog.objects.create(
        lot=lot,
        field_name="expiration_date",
        old_value=_date_iso(old_exp),
        new_value=_date_iso(new_exp),
        reason=(
            f"Shelf life extension +{months} mo from QC {qc_date.isoformat()}"
            + (f": {(notes or '').strip()}" if (notes or "").strip() else "")
        )[:500],
        changed_by=who,
    )

    cert = LotCoaCertificate.objects.filter(lot=lot).select_related("lot", "lot__item").first()
    if cert is not None:
        # Keep micro line_results; update QC snapshots / optional result
        if qname:
            cert.qc_parameter_name_snapshot = qname
            cert.qc_spec_min_snapshot = qmin
            cert.qc_spec_max_snapshot = qmax
        if qc_result_value is not None:
            cert.qc_result_value = qc_result_value
            cert.qc_result_pass = qc_pass
        cert.recorded_by = who or cert.recorded_by
        cert.save()

    # Create SLE before PDF so build_master_coa_context picks up the banner.
    ext = LotShelfLifeExtension.objects.create(
        lot=lot,
        qc_date=qc_date,
        extension_months=months,
        previous_expiration=old_exp,
        new_expiration=new_exp,
        qc_parameter_name=qname,
        qc_spec_min=qmin,
        qc_spec_max=qmax,
        qc_result_value=qc_result_value,
        notes=(notes or "").strip(),
        certificate=cert,
        recorded_by=who,
    )

    if cert is not None:
        save_coa_pdf_to_certificate(cert)

    return ext
