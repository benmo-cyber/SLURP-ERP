"""
Campaign COA: composite certificate across production batches linked to a CampaignLot.

- QC: net-yield-weighted mean of member lot QC results
- Micros: highest numeric per test across member lots (pass/fail → Pass)
- Mfg: first calendar day any member batch closed
- Exp: mfg + formula/FPS shelf_life_months
- Issue when every member output lot is fully released (has master COA, not on hold)
- Re-issue creates a new CampaignCoaCertificate version (never overwrite)
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .make_services import net_yield_native


class CampaignCoaError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _as_aware_midnight(d: date):
    dt = datetime.combine(d, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def _local_date(dt) -> date | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if isinstance(dt, datetime):
        local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
        return local.date()
    return None


def _parse_numeric_result(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Prefer last number in the string (e.g. "< 10", "≤ 1000 CFU/g")
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text.replace(",", ""))
    if not nums:
        return None
    try:
        return float(nums[-1])
    except (TypeError, ValueError):
        return None


def campaign_batches(campaign):
    from .models import ProductionBatch

    return list(
        ProductionBatch.objects.filter(campaign=campaign)
        .select_related("finished_good_item", "formula")
        .order_by("id")
    )


def campaign_output_lots(campaign) -> list:
    """Output lots for closed/open campaign batches (one lot per batch when present)."""
    from .models import ProductionBatchOutput

    batches = campaign_batches(campaign)
    if not batches:
        return []
    batch_ids = [b.id for b in batches]
    outs = (
        ProductionBatchOutput.objects.filter(batch_id__in=batch_ids)
        .select_related("lot", "lot__item", "batch")
        .order_by("batch_id", "id")
    )
    by_batch: dict[int, Any] = {}
    for o in outs:
        if o.batch_id not in by_batch and o.lot_id:
            by_batch[o.batch_id] = o.lot
    return [by_batch[b.id] for b in batches if b.id in by_batch]


def lot_is_fully_released(lot) -> bool:
    """Released for campaign COA: master COA exists and nothing on hold."""
    from .models import LotCoaCertificate

    if lot is None:
        return False
    hold = float(getattr(lot, "quantity_on_hold", 0) or 0)
    if hold > 1e-6:
        return False
    return LotCoaCertificate.objects.filter(lot_id=lot.pk).exists()


def campaign_release_status(campaign) -> dict[str, Any]:
    """
    Readiness for campaign COA issue.

    Returns counts and whether ready. Singleton campaigns (≤1 batch) are never
    treated as campaign-COA candidates.
    """
    batches = campaign_batches(campaign)
    n_batches = len(batches)
    lots = campaign_output_lots(campaign)
    n_lots = len(lots)
    n_closed = sum(1 for b in batches if b.status == "closed")
    n_released = sum(1 for lot in lots if lot_is_fully_released(lot))
    # Each closed batch should have an output lot; wait for all batches closed
    # and every output lot released.
    waiting_releases = max(0, n_batches - n_released)
    ready = (
        n_batches >= 2
        and n_closed == n_batches
        and n_lots == n_batches
        and n_released == n_batches
    )
    return {
        "batch_count": n_batches,
        "closed_count": n_closed,
        "lot_count": n_lots,
        "released_count": n_released,
        "waiting_releases": waiting_releases,
        "ready": ready,
        "lots": lots,
        "batches": batches,
    }


def campaign_first_close_date(campaign) -> date | None:
    batches = campaign_batches(campaign)
    dates = []
    for b in batches:
        if b.status != "closed":
            continue
        d = _local_date(b.closed_date) or _local_date(b.production_date)
        if d:
            dates.append(d)
    return min(dates) if dates else None


def campaign_member_net_yield(batch) -> float:
    """Net yield mass used as QC weight; fall back to quantity_produced."""
    net = net_yield_native(batch)
    if net is not None and float(net) > 0:
        return float(net)
    return float(batch.quantity_produced or 0)


def _lot_cert(lot):
    from .models import LotCoaCertificate

    return (
        LotCoaCertificate.objects.filter(lot=lot)
        .prefetch_related("line_results", "line_results__item_line")
        .first()
    )


def compute_weighted_qc(lots_and_batches: list[tuple]) -> dict[str, Any]:
    """
    lots_and_batches: [(lot, batch), ...]
    Returns qc snapshots + weighted mean value.
    """
    from .coa_logic import evaluate_qc_numeric_pass

    total_w = 0.0
    weighted = 0.0
    qname = ""
    qmin = qmax = None
    for lot, batch in lots_and_batches:
        cert = _lot_cert(lot)
        if cert is None or cert.qc_result_value is None:
            continue
        w = campaign_member_net_yield(batch)
        if w <= 0:
            continue
        if not qname:
            qname = (cert.qc_parameter_name_snapshot or "").strip()
            qmin = cert.qc_spec_min_snapshot
            qmax = cert.qc_spec_max_snapshot
        total_w += w
        weighted += float(cert.qc_result_value) * w
    if total_w <= 0 or not qname:
        return {
            "qc_parameter_name_snapshot": qname,
            "qc_spec_min_snapshot": qmin,
            "qc_spec_max_snapshot": qmax,
            "qc_result_value": None,
            "qc_result_pass": None,
        }
    val = round(weighted / total_w, 6)
    return {
        "qc_parameter_name_snapshot": qname,
        "qc_spec_min_snapshot": qmin,
        "qc_spec_max_snapshot": qmax,
        "qc_result_value": val,
        "qc_result_pass": evaluate_qc_numeric_pass(val, qmin, qmax),
    }


def compute_max_micro_lines(lots: list) -> list[dict[str, Any]]:
    """
    Per test_name across member lot COAs: highest numeric result.
    Pass/fail and non-numeric → Pass (failed lots would have been scrapped).
    """
    from .coa_logic import evaluate_item_line_pass

    by_name: dict[str, dict[str, Any]] = {}
    for lot in lots:
        cert = _lot_cert(lot)
        if cert is None:
            continue
        for lr in cert.line_results.all():
            name = (lr.test_name or "").strip()
            if not name:
                continue
            entry = by_name.setdefault(
                name,
                {
                    "test_name": name,
                    "specification_text": lr.specification_text or "",
                    "item_line": lr.item_line,
                    "numeric_max": None,
                    "any_pass_fail_or_text": False,
                    "result_texts": [],
                },
            )
            if not entry["specification_text"] and lr.specification_text:
                entry["specification_text"] = lr.specification_text
            if entry["item_line"] is None and lr.item_line_id:
                entry["item_line"] = lr.item_line
            kind = (
                getattr(lr.item_line, "result_kind", None) if lr.item_line_id else None
            ) or "text_only"
            num = _parse_numeric_result(lr.result_text)
            if kind in ("numeric_range", "numeric_minimum") or (
                num is not None and kind not in ("pass_fail", "text_only")
            ):
                if num is not None:
                    cur = entry["numeric_max"]
                    entry["numeric_max"] = num if cur is None else max(cur, num)
            else:
                entry["any_pass_fail_or_text"] = True
            entry["result_texts"].append(lr.result_text or "")

    rows = []
    for name, entry in by_name.items():
        item_line = entry["item_line"]
        if entry["numeric_max"] is not None:
            result_text = f"{entry['numeric_max']:g}"
            passes = (
                evaluate_item_line_pass(item_line, result_text)
                if item_line is not None
                else None
            )
        else:
            # Text / pass-fail: Pass (scrap path would remove failing lots).
            result_text = "Pass"
            passes = True
        rows.append(
            {
                "item_line": item_line,
                "test_name": name,
                "specification_text": entry["specification_text"],
                "result_text": result_text[:500],
                "passes": passes,
            }
        )
    rows.sort(key=lambda r: (r["test_name"] or "").lower())
    return rows


def current_campaign_coa(campaign):
    from .models import CampaignCoaCertificate

    return (
        CampaignCoaCertificate.objects.filter(campaign=campaign, is_current=True)
        .prefetch_related("line_results")
        .first()
    )


def shelf_life_months_for_campaign(campaign) -> int | None:
    from .formula_resolve import formula_for_item

    item = campaign.item
    f = formula_for_item(getattr(item, "id", None))
    if f and f.shelf_life_months:
        return int(f.shelf_life_months)
    # Fall back to any member batch formula
    for b in campaign_batches(campaign):
        fb = getattr(b, "formula", None)
        if fb and fb.shelf_life_months:
            return int(fb.shelf_life_months)
        if b.finished_good_item_id:
            f2 = formula_for_item(b.finished_good_item_id)
            if f2 and f2.shelf_life_months:
                return int(f2.shelf_life_months)
    return None


@transaction.atomic
def issue_or_reissue_campaign_coa(
    campaign,
    *,
    user=None,
    force: bool = False,
    notes: str = "",
) -> Any | None:
    """
    Build campaign COA when ready. If a current COA already exists, create a new
    version (re-issue) unless content would be identical and force is False.

    Returns the new/current CampaignCoaCertificate, or None if not ready.
    """
    from .coa_pdf_html import save_campaign_coa_pdf
    from .lot_date_utils import add_calendar_months_to_datetime
    from .models import CampaignCoaCertificate, CampaignCoaLineResult

    status = campaign_release_status(campaign)
    if not status["ready"]:
        return None

    batches = status["batches"]
    lots = status["lots"]
    by_lot_id = {lot.id: lot for lot in lots}
    pairs = []
    for b in batches:
        # Match output lot for this batch
        from .models import ProductionBatchOutput

        out = (
            ProductionBatchOutput.objects.filter(batch=b)
            .select_related("lot")
            .order_by("id")
            .first()
        )
        if out and out.lot_id and out.lot_id in by_lot_id:
            pairs.append((by_lot_id[out.lot_id], b))

    mfg = campaign_first_close_date(campaign)
    if mfg is None:
        raise CampaignCoaError("Cannot determine campaign manufacture date.")
    months = shelf_life_months_for_campaign(campaign)
    if not months:
        raise CampaignCoaError(
            "Finished product has no shelf_life_months on its formula/FPS."
        )
    exp = add_calendar_months_to_datetime(_as_aware_midnight(mfg), months)

    qc = compute_weighted_qc(pairs)
    lines = compute_max_micro_lines(lots)
    qty = round(sum(campaign_member_net_yield(b) for _lot, b in pairs), 2)

    existing = current_campaign_coa(campaign)
    next_version = (existing.version + 1) if existing else 1
    who = ""
    if existing is None:
        who = (
            getattr(user, "username", None)
            or getattr(user, "get_username", lambda: "")()
            or ""
        )
        # Prefer explicit initials if passed via notes prefix — keep username.

    # Always re-issue when called after a membership/release change (force) or
    # when no current exists. Skip no-op only when force=False and values match.
    if existing is not None and not force:
        same_qc = (
            existing.qc_result_value == qc["qc_result_value"]
            or (
                existing.qc_result_value is not None
                and qc["qc_result_value"] is not None
                and abs(float(existing.qc_result_value) - float(qc["qc_result_value"]))
                < 1e-6
            )
        )
        same_mfg = existing.manufacture_date == mfg
        n_lines = existing.line_results.count()
        if same_qc and same_mfg and n_lines == len(lines):
            return existing

    if existing is not None:
        CampaignCoaCertificate.objects.filter(pk=existing.pk).update(is_current=False)

    cert = CampaignCoaCertificate.objects.create(
        campaign=campaign,
        version=next_version,
        is_current=True,
        manufacture_date=mfg,
        expiration_date=exp,
        quantity_snapshot=qty,
        qc_parameter_name_snapshot=qc["qc_parameter_name_snapshot"] or "",
        qc_spec_min_snapshot=qc["qc_spec_min_snapshot"],
        qc_spec_max_snapshot=qc["qc_spec_max_snapshot"],
        qc_result_value=qc["qc_result_value"],
        qc_result_pass=qc["qc_result_pass"],
        recorded_by=who or (existing.recorded_by if existing else ""),
        notes=(notes or "").strip(),
    )
    for row in lines:
        CampaignCoaLineResult.objects.create(
            certificate=cert,
            item_line=row["item_line"],
            test_name=row["test_name"],
            specification_text=row["specification_text"],
            result_text=row["result_text"],
            passes=row["passes"],
        )

    save_campaign_coa_pdf(cert)

    # Refresh member batch master PDFs (campaign code + 8pt batch lot) and
    # customer copies so they can default to campaign basis.
    from .coa_allocation import sync_customer_coas_for_lot
    from .coa_pdf_html import save_coa_pdf_to_certificate
    from .models import LotCoaCertificate

    for lot in lots:
        lot_cert = LotCoaCertificate.objects.filter(lot=lot).first()
        if lot_cert is not None:
            try:
                save_coa_pdf_to_certificate(lot_cert)
            except Exception:
                pass
        try:
            sync_customer_coas_for_lot(lot.id)
        except Exception:
            pass

    return cert


def maybe_issue_campaign_coa_for_lot(lot, user=None) -> Any | None:
    """After a lot release: if lot's batch is in a ready campaign, issue/re-issue."""
    from .models import ProductionBatchOutput

    out = (
        ProductionBatchOutput.objects.filter(lot=lot)
        .select_related("batch__campaign")
        .order_by("-id")
        .first()
    )
    if out is None or not out.batch_id or not out.batch.campaign_id:
        return None
    camp = out.batch.campaign
    status = campaign_release_status(camp)
    if status["batch_count"] < 2:
        return None
    if not status["ready"]:
        return None
    return issue_or_reissue_campaign_coa(camp, user=user, force=True)


def lot_campaign(lot):
    """Return CampaignLot if this lot is an output of a multi-batch campaign."""
    from .models import ProductionBatchOutput

    out = (
        ProductionBatchOutput.objects.filter(lot=lot)
        .select_related("batch__campaign")
        .order_by("-id")
        .first()
    )
    if out is None or not out.batch.campaign_id:
        return None
    camp = out.batch.campaign
    n = camp.batches.count()
    if n < 2:
        return None
    return camp


def lot_in_multi_batch_campaign(lot) -> bool:
    return lot_campaign(lot) is not None
