"""
Shared lot inventory actions: hold, release (+ COA), reconcile, indirect checkout.

Used by DRF LotViewSet and slurp_ui templates.
"""
from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from .lot_display_quantities import compute_lot_quantity_breakdown
from .models import InventoryTransaction, Lot

logger = logging.getLogger(__name__)


class LotFlowError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def checkout_indirect_material(user, lot: Lot, quantity: float, notes: str = "", reference_number: str = "") -> Lot:
    from .views import log_lot_transaction

    if lot.item.item_type != "indirect_material":
        raise LotFlowError("This lot is not an indirect material")

    try:
        quantity = round(float(quantity), 2)
    except (TypeError, ValueError):
        raise LotFlowError("Valid quantity is required")
    if quantity <= 0:
        raise LotFlowError("Valid quantity is required")

    max_use = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
    if quantity > max_use + 1e-6:
        raise LotFlowError(f"Insufficient quantity. Available: {max_use}, Requested: {quantity}")

    quantity_before = lot.quantity_remaining
    txn = InventoryTransaction.objects.create(
        transaction_type="indirect_material_checkout",
        lot=lot,
        quantity=round(-quantity, 2),
        notes=notes or f"Indirect material checkout - {lot.item.name}",
        reference_number=reference_number,
    )
    log_lot_transaction(
        lot=lot,
        quantity_before=quantity_before,
        quantity_change=-quantity,
        transaction_type="indirect_material_checkout",
        reference_number=reference_number,
        reference_type="checkout",
        transaction_id=txn.id,
        notes=notes or f"Indirect material checkout - {lot.item.name}",
    )
    lot.quantity_remaining = round(lot.quantity_remaining - quantity, 2)
    lot.save()
    return lot


def put_on_hold(lot: Lot, quantity: float) -> Lot:
    try:
        quantity = round(float(quantity), 2)
    except (TypeError, ValueError):
        raise LotFlowError("Valid quantity is required")
    if quantity <= 0:
        raise LotFlowError("Quantity must be positive")

    available = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
    if quantity > available:
        raise LotFlowError(
            f"Only {available} available to put on hold "
            "(remaining minus sales/prod allocations and current on hold)"
        )

    current_hold = getattr(lot, "quantity_on_hold", 0.0) or 0.0
    lot.quantity_on_hold = round(current_hold + quantity, 2)
    lot.on_hold = True
    if lot.quantity_on_hold >= lot.quantity_remaining:
        lot.status = "on_hold"
    lot.save(update_fields=["quantity_on_hold", "on_hold", "status"])
    return lot


def coa_release_preview(lot: Lot, release_qty: float) -> dict[str, Any]:
    from .coa_logic import coa_required_for_full_release, manufactured_item_types
    from .models import Formula, ItemCoaTestLine, LotCoaCertificate
    from .serializers import ItemCoaTestLineSerializer

    try:
        rq = round(float(release_qty), 2)
    except (TypeError, ValueError):
        raise LotFlowError("release_qty is required (number)")
    if rq <= 0:
        raise LotFlowError("release_qty must be positive")

    current_hold = float(getattr(lot, "quantity_on_hold", 0.0) or 0.0)
    if rq > current_hold + 1e-6:
        raise LotFlowError(f"Only {current_hold} on hold; cannot release more than that")

    new_hold = round(current_hold - rq, 2)
    full_clear = new_hold <= 0
    has_cert = LotCoaCertificate.objects.filter(lot=lot).exists()
    coa_required = bool(full_clear and coa_required_for_full_release(lot) and not has_cert)

    lines = []
    if getattr(lot.item, "item_type", None) in manufactured_item_types():
        lines = ItemCoaTestLineSerializer(
            ItemCoaTestLine.objects.filter(item=lot.item).order_by("sort_order", "id"),
            many=True,
        ).data

    formula_qc = None
    try:
        f = Formula.objects.get(finished_good_id=lot.item_id)
        if (f.qc_parameter_name or "").strip():
            formula_qc = {
                "qc_parameter_name": f.qc_parameter_name,
                "qc_spec_min": f.qc_spec_min,
                "qc_spec_max": f.qc_spec_max,
            }
    except Formula.DoesNotExist:
        pass

    return {
        "full_clear_from_hold": full_clear,
        "coa_required": coa_required,
        "template_lines": lines,
        "formula_qc": formula_qc,
    }


def release_from_hold(user, lot: Lot, quantity: float, coa_payload: dict | None = None) -> Lot:
    from .coa_allocation import sync_customer_coas_for_lot
    from .coa_logic import (
        coa_required_for_full_release,
        evaluate_item_line_pass,
        evaluate_qc_numeric_pass,
    )
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .models import Formula, ItemCoaTestLine, LotCoaCertificate, LotCoaLineResult

    try:
        quantity = round(float(quantity), 2)
    except (TypeError, ValueError):
        raise LotFlowError("Valid quantity is required")
    if quantity <= 0:
        raise LotFlowError("Quantity must be positive")

    current_hold = float(getattr(lot, "quantity_on_hold", 0.0) or 0.0)
    if quantity > current_hold:
        raise LotFlowError(f"Only {current_hold} on hold; cannot release more")

    new_hold = round(current_hold - quantity, 2)
    will_full_clear = new_hold <= 0
    needs_coa = (
        will_full_clear
        and coa_required_for_full_release(lot)
        and not LotCoaCertificate.objects.filter(lot=lot).exists()
    )

    lines_qs: list = []
    by_id: dict[int, str] = {}
    has_qc = False
    formula = None
    qc_val = None

    if needs_coa:
        if not isinstance(coa_payload, dict):
            raise LotFlowError(
                "This release clears hold on a manufactured lot. Enter micro/QC results. "
                "Use the release form with COA fields (coa_required)."
            )
        lines_qs = list(ItemCoaTestLine.objects.filter(item=lot.item).order_by("sort_order", "id"))
        for row in coa_payload.get("line_results") or []:
            try:
                lid = int(row.get("item_line_id"))
                by_id[lid] = (row.get("result_text") or "").strip()
            except (TypeError, ValueError):
                continue
        for line in lines_qs:
            if line.id not in by_id:
                raise LotFlowError(f"Missing micro/COA result for line: {line.test_name}")
        try:
            formula = Formula.objects.get(finished_good_id=lot.item_id)
        except Formula.DoesNotExist:
            formula = None
        has_qc = bool(formula and (formula.qc_parameter_name or "").strip())
        if has_qc:
            raw_qc = coa_payload.get("qc_result_value")
            if raw_qc is None or (isinstance(raw_qc, str) and not str(raw_qc).strip()):
                raise LotFlowError(f"QC result required for parameter: {formula.qc_parameter_name}")
            try:
                qc_val = float(raw_qc)
            except (TypeError, ValueError):
                raise LotFlowError("qc_result_value must be a number")

    with transaction.atomic():
        lot_locked = Lot.objects.select_for_update().get(pk=lot.pk)
        ch = float(getattr(lot_locked, "quantity_on_hold", 0.0) or 0.0)
        if quantity > ch:
            raise ValidationError(f"Only {ch} on hold; cannot release more")
        nh = round(ch - quantity, 2)
        full_clear = nh <= 0
        if full_clear:
            nh = 0.0

        need_cert_here = (
            full_clear
            and coa_required_for_full_release(lot_locked)
            and not LotCoaCertificate.objects.filter(lot=lot_locked).exists()
        )
        if need_cert_here and not isinstance(coa_payload, dict):
            raise ValidationError("COA payload required")

        lot_locked.quantity_on_hold = nh
        if lot_locked.quantity_on_hold <= 0:
            lot_locked.quantity_on_hold = 0.0
            lot_locked.on_hold = False
            lot_locked.status = "accepted"
        else:
            lot_locked.on_hold = True
            lot_locked.status = "on_hold"
        lot_locked.save(update_fields=["quantity_on_hold", "on_hold", "status"])

        if need_cert_here:
            cert = LotCoaCertificate(
                lot=lot_locked,
                customer_name="",
                customer_po="",
                quantity_snapshot=float(lot_locked.quantity_remaining or 0),
                recorded_by=getattr(user, "username", None) or getattr(user, "email", None) or "",
            )
            if has_qc and formula:
                cert.qc_parameter_name_snapshot = formula.qc_parameter_name or ""
                cert.qc_spec_min_snapshot = formula.qc_spec_min
                cert.qc_spec_max_snapshot = formula.qc_spec_max
                cert.qc_result_value = qc_val
                cert.qc_result_pass = evaluate_qc_numeric_pass(
                    qc_val, formula.qc_spec_min, formula.qc_spec_max
                )
            cert.save()

            for line in lines_qs:
                rt = by_id.get(line.id, "")
                passes = evaluate_item_line_pass(line, rt)
                LotCoaLineResult.objects.create(
                    certificate=cert,
                    item_line=line,
                    test_name=line.test_name,
                    specification_text=line.specification_text,
                    result_text=str(rt)[:500],
                    passes=passes,
                )

            save_coa_pdf_to_certificate(cert)
            lot_pk = lot_locked.pk
            transaction.on_commit(lambda pk=lot_pk: sync_customer_coas_for_lot(pk))

    lot_locked.refresh_from_db()
    return lot_locked


def reconcile_lot(user, lot: Lot, quantity_remaining: float, reason: str = "") -> Lot:
    if not getattr(user, "is_authenticated", True) or (
        not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False)
    ):
        raise LotFlowError("Admin override requires staff or superuser.", status_code=403)

    try:
        new_remaining = round(float(quantity_remaining), 2)
    except (TypeError, ValueError):
        raise LotFlowError("Valid quantity_remaining is required")
    if new_remaining < 0:
        raise LotFlowError("quantity_remaining cannot be negative")

    reason = (reason or "").strip() or "Admin reconcile"
    quantity_before = lot.quantity_remaining
    quantity_change = new_remaining - quantity_before
    if quantity_change == 0:
        return lot

    lot.quantity_remaining = new_remaining
    if new_remaining > 0:
        lot.depleted_at = None
    lot.save(update_fields=["quantity_remaining", "depleted_at"])

    try:
        from .models import LotTransactionLog

        LotTransactionLog.objects.create(
            lot=lot,
            lot_number=lot.lot_number or "",
            item_sku=lot.item.sku,
            item_name=lot.item.name,
            vendor=lot.item.vendor or "",
            transaction_type="adjustment",
            quantity_before=quantity_before,
            quantity_change=quantity_change,
            quantity_after=new_remaining,
            unit_of_measure=lot.item.unit_of_measure,
            reference_number=None,
            reference_type="admin_reconcile",
            notes=reason,
            logged_by=getattr(user, "username", None) or getattr(user, "email", None) or "admin",
        )
    except Exception as e:
        logger.warning("Failed to log reconcile: %s", e)

    return lot
