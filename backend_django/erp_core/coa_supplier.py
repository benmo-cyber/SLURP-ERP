"""
Supplier-backed lot COA: issue at check-in from ItemCoaTestLine results; clone on relabel.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)


class SupplierCoaError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def item_has_supplier_coa_profile(item) -> bool:
    """True when the item has COA / typical micro lines (FG or distributed)."""
    if not item or not getattr(item, "id", None):
        return False
    from .models import ItemCoaTestLine

    return ItemCoaTestLine.objects.filter(item_id=item.id).exists()


def coa_lines_for_item(item_id: int):
    from .models import ItemCoaTestLine

    return list(
        ItemCoaTestLine.objects.filter(item_id=item_id).order_by("sort_order", "id")
    )


def issue_supplier_coa_for_lot(
    lot,
    user,
    line_results: list[dict] | None,
    *,
    require_all_lines: bool = True,
    source_lot=None,
) -> Any:
    """
    Create LotCoaCertificate (source=supplier) from ItemCoaTestLine + entered results.

    ``line_results``: [{item_line_id, result_text}, ...]
    Raises SupplierCoaError if profile exists and results are incomplete.
    Returns the certificate, or None if the item has no COA profile.
    """
    from .coa_logic import evaluate_item_line_pass
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .models import LotCoaCertificate, LotCoaLineResult

    item = getattr(lot, "item", None)
    if not item:
        return None

    lines_qs = coa_lines_for_item(item.id)
    if not lines_qs:
        return None

    if LotCoaCertificate.objects.filter(lot_id=lot.id).exists():
        return LotCoaCertificate.objects.get(lot_id=lot.id)

    by_id: dict[int, str] = {}
    for row in line_results or []:
        if not isinstance(row, dict):
            continue
        try:
            lid = int(row.get("item_line_id"))
        except (TypeError, ValueError):
            continue
        by_id[lid] = (row.get("result_text") or "").strip()

    if require_all_lines:
        missing = [ln.test_name for ln in lines_qs if ln.id not in by_id or not by_id[ln.id]]
        if missing:
            raise SupplierCoaError(
                "Enter supplier COA results for: " + "; ".join(missing[:8])
                + ("…" if len(missing) > 8 else "")
            )

    recorded = (
        getattr(user, "username", None) or getattr(user, "email", None) or ""
    )

    with transaction.atomic():
        cert = LotCoaCertificate(
            lot=lot,
            source="supplier",
            source_lot=source_lot,
            customer_name="",
            customer_po="",
            quantity_snapshot=float(getattr(lot, "quantity_remaining", None) or getattr(lot, "quantity", 0) or 0),
            recorded_by=recorded,
        )
        cert.save()

        for line in lines_qs:
            rt = by_id.get(line.id, "") or (line.typical_result or "").strip()
            passes = evaluate_item_line_pass(line, rt) if rt else None
            LotCoaLineResult.objects.create(
                certificate=cert,
                item_line=line,
                test_name=line.test_name,
                specification_text=line.specification_text,
                result_text=str(rt)[:500],
                passes=passes,
            )

        try:
            save_coa_pdf_to_certificate(cert)
        except Exception:
            logger.exception("save_coa_pdf_to_certificate failed for supplier COA lot %s", lot.pk)

    return cert


def missing_supplier_coa_profile_lines(lot) -> list:
    """FPS profile lines not yet present on the lot's master COA (by item_line or name)."""
    from .models import LotCoaCertificate

    if not lot or not getattr(lot, "item_id", None):
        return []
    profile = coa_lines_for_item(lot.item_id)
    if not profile:
        return []
    try:
        cert = LotCoaCertificate.objects.prefetch_related("line_results").get(lot_id=lot.id)
    except LotCoaCertificate.DoesNotExist:
        return profile

    have_ids = {
        int(lr.item_line_id)
        for lr in cert.line_results.all()
        if lr.item_line_id is not None
    }
    have_names = {
        (lr.test_name or "").strip().casefold()
        for lr in cert.line_results.all()
        if (lr.test_name or "").strip()
    }
    missing = []
    for ln in profile:
        name_key = (ln.test_name or "").strip().casefold()
        if ln.id in have_ids or (name_key and name_key in have_names):
            continue
        missing.append(ln)
    return missing


def complete_supplier_coa_for_lot(
    lot,
    user,
    line_results: list[dict] | None,
    *,
    require_all_missing: bool = True,
) -> Any:
    """
    Append missing FPS profile lines onto an existing supplier (or any) master COA.
    If no cert exists, delegates to issue_supplier_coa_for_lot.
    """
    from .coa_logic import evaluate_item_line_pass
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .models import LotCoaCertificate, LotCoaLineResult

    missing = missing_supplier_coa_profile_lines(lot)
    if not LotCoaCertificate.objects.filter(lot_id=lot.id).exists():
        return issue_supplier_coa_for_lot(
            lot, user, line_results, require_all_lines=True
        )
    if not missing:
        return LotCoaCertificate.objects.get(lot_id=lot.id)

    by_id: dict[int, str] = {}
    for row in line_results or []:
        if not isinstance(row, dict):
            continue
        try:
            lid = int(row.get("item_line_id"))
        except (TypeError, ValueError):
            continue
        by_id[lid] = (row.get("result_text") or "").strip()

    if require_all_missing:
        still = [ln.test_name for ln in missing if ln.id not in by_id or not by_id[ln.id]]
        if still:
            raise SupplierCoaError(
                "Enter supplier COA results for: " + "; ".join(still[:8])
                + ("…" if len(still) > 8 else "")
            )

    cert = LotCoaCertificate.objects.get(lot_id=lot.id)
    with transaction.atomic():
        for line in missing:
            rt = by_id.get(line.id, "") or (line.typical_result or "").strip()
            passes = evaluate_item_line_pass(line, rt) if rt else None
            LotCoaLineResult.objects.create(
                certificate=cert,
                item_line=line,
                test_name=line.test_name,
                specification_text=line.specification_text,
                result_text=str(rt)[:500],
                passes=passes,
            )
        try:
            save_coa_pdf_to_certificate(cert)
        except Exception:
            logger.exception(
                "save_coa_pdf_to_certificate failed completing COA for lot %s", lot.pk
            )
    return cert


def clone_lot_coa_certificate(source_lot, dest_lot, user=None) -> Any:
    """
    Copy master COA from source_lot onto dest_lot (relabel output).
    No-op if source has no cert or dest already has one.
    """
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .models import LotCoaCertificate, LotCoaLineResult

    try:
        src = LotCoaCertificate.objects.prefetch_related("line_results").get(lot_id=source_lot.id)
    except LotCoaCertificate.DoesNotExist:
        return None

    if LotCoaCertificate.objects.filter(lot_id=dest_lot.id).exists():
        return LotCoaCertificate.objects.get(lot_id=dest_lot.id)

    recorded = (
        getattr(user, "username", None) or getattr(user, "email", None) or src.recorded_by or ""
    )

    with transaction.atomic():
        cert = LotCoaCertificate.objects.create(
            lot=dest_lot,
            source=src.source or "supplier",
            source_lot=source_lot,
            customer_name="",
            customer_po="",
            quantity_snapshot=float(
                getattr(dest_lot, "quantity_remaining", None)
                or getattr(dest_lot, "quantity", 0)
                or 0
            ),
            qc_parameter_name_snapshot=src.qc_parameter_name_snapshot or "",
            qc_spec_min_snapshot=src.qc_spec_min_snapshot,
            qc_spec_max_snapshot=src.qc_spec_max_snapshot,
            qc_result_value=src.qc_result_value,
            qc_result_pass=src.qc_result_pass,
            recorded_by=recorded,
        )
        for lr in src.line_results.all():
            LotCoaLineResult.objects.create(
                certificate=cert,
                item_line_id=lr.item_line_id,
                test_name=lr.test_name,
                specification_text=lr.specification_text,
                result_text=lr.result_text,
                passes=lr.passes,
            )
        try:
            save_coa_pdf_to_certificate(cert)
        except Exception:
            logger.exception(
                "save_coa_pdf_to_certificate failed cloning COA %s → lot %s",
                src.pk,
                dest_lot.pk,
            )
    return cert
