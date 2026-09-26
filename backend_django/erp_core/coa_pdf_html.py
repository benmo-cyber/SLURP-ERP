"""Lot Certificate of Analysis: Jinja2 HTML → PDF (xhtml2pdf)."""
from datetime import date, datetime
from pathlib import Path
import logging

from django.utils import timezone

from .html_pdf_common import html_string_to_pdf_bytes
from .pdf_generator import get_batch_ticket_logo_base64_cached

logger = logging.getLogger(__name__)


def _s(val):
    if val is None:
        return ""
    text = str(val)
    # xhtml2pdf/Helvetica cannot draw these; keep COA cells readable
    return (
        text.replace("\u2264", "<=")  # ≤
        .replace("\u2265", ">=")  # ≥
        .replace("\u00b1", "+/-")  # ±
        .replace("\u2013", "-")  # –
        .replace("\u2014", "-")  # —
    )


def _format_qty_display(qty, uom: str) -> str:
    try:
        q = float(qty)
        qty_s = f"{q:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        qty_s = _s(qty)
    return f"{qty_s} {(uom or 'lbs')}".strip()


def _to_display_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):
        return val.date()
    return val


def _test_rows_from_certificate(
    certificate,
    *,
    include_ids=None,
    include_qc: bool = True,
    display_mode: str = "actual",
    line_overrides: dict | None = None,
    spec_overrides: dict | None = None,
):
    """
    Build Test | Specification | Result rows for a COA PDF.

    Master path: include_ids=None, include_qc=True, display_mode='actual'.
    Customer path: filter by include_ids / include_qc; display_mode may be
    actual | pass_fail | per_line (with line_overrides); spec_overrides may
    replace printed Spec per line id (customer requirements).
    """
    from .coa_customer_options import _pass_fail_label
    from .coa_logic import qc_spec_display

    mode = (display_mode or "actual").strip().lower()
    overrides = line_overrides or {}
    specs = {str(k): v for k, v in (spec_overrides or {}).items()}
    test_rows = []

    qname = (certificate.qc_parameter_name_snapshot or "").strip()
    has_qc = bool(qname or certificate.qc_result_value is not None)
    if include_qc and has_qc:
        spec = qc_spec_display(
            qname or "QC",
            certificate.qc_spec_min_snapshot,
            certificate.qc_spec_max_snapshot,
        )
        qc_disp = mode
        if mode == "per_line":
            qc_disp = overrides.get("qc", "actual")
        if qc_disp == "pass_fail":
            res = _pass_fail_label(certificate.qc_result_pass)
        elif certificate.qc_result_value is not None:
            res = f"{float(certificate.qc_result_value):g}"
        else:
            res = "—"
        test_rows.append({"test": qname or "QC parameter", "specification": spec, "result": res})

    id_filter = None
    if include_ids is not None:
        id_filter = {int(x) for x in include_ids}

    for lr in certificate.line_results.all().order_by("id"):
        if id_filter is not None and int(lr.id) not in id_filter:
            continue
        line_mode = mode
        if mode == "per_line":
            line_mode = overrides.get(str(lr.id), "actual")
        if line_mode == "pass_fail":
            # text_only / unevaluated lines store passes=None — show the recorded result
            # instead of a blank "—" on the customer COA.
            if lr.passes is None:
                res = _s(lr.result_text) or _pass_fail_label(None)
            else:
                res = _pass_fail_label(lr.passes)
        else:
            res = _s(lr.result_text)
        printed_spec = specs.get(str(lr.id))
        if printed_spec is not None and str(printed_spec).strip():
            spec_text = _s(printed_spec)
        else:
            spec_text = _s(lr.specification_text)
        test_rows.append(
            {
                "test": _s(lr.test_name),
                "specification": spec_text,
                "result": res,
            }
        )
    return test_rows


def _dates_from_lot(lot):
    """Manuf. / exp from the lot row (same fields as inventory). Calendar only; shows — when unset.

    Manuf. falls back to the producing batch close date, then lot received_date, so COAs
    stay correct when manufacture_date was not written at close.

    Exp falls back to manufacture + formula.shelf_life_months when lot.expiration_date
    is unset (Master COA must still print a date). Shelf-life extensions write
    expiration_date explicitly, so those take precedence.
    """
    md = getattr(lot, "manufacture_date", None)
    if md is None and lot is not None:
        try:
            from .models import ProductionBatchOutput

            closed = (
                ProductionBatchOutput.objects.filter(lot_id=lot.pk)
                .exclude(batch__closed_date__isnull=True)
                .order_by("-batch__closed_date")
                .values_list("batch__closed_date", flat=True)
                .first()
            )
            md = closed or getattr(lot, "received_date", None)
        except Exception:
            md = getattr(lot, "received_date", None)
    d = _to_display_date(md)
    manufacture_date = d.strftime("%B %d, %Y") if d else "—"

    ed = getattr(lot, "expiration_date", None)
    if ed is None and d is not None and lot is not None:
        try:
            from .formula_resolve import formula_for_lot
            from .lot_date_utils import add_calendar_months_to_datetime
            from .views import _expiration_datetime_for_fg_output

            base_dt = getattr(lot, "manufacture_date", None) or md
            # Batch-locked formula first (multi-recipe FGs), then item default.
            formula = formula_for_lot(lot)
            computed = _expiration_datetime_for_fg_output(
                lot.item, base_dt, formula=formula
            )
            if computed is None and formula and formula.shelf_life_months:
                computed = add_calendar_months_to_datetime(
                    base_dt, int(formula.shelf_life_months)
                )
            ed = computed
        except Exception:
            ed = None
    d_exp = _to_display_date(ed)
    expiration_date = d_exp.strftime("%B %d, %Y") if d_exp else "—"

    return manufacture_date, expiration_date


def build_coa_template_context(
    *,
    product_name: str,
    lot_number: str,
    quantity_display: str,
    customer_name: str,
    customer_po: str,
    manufacture_date: str,
    expiration_date: str,
    issue_date: str,
    test_rows: list,
    is_example: bool = False,
    shelf_life_extension=None,
    batch_lot_trace: str = "",
):
    logo_base64 = get_batch_ticket_logo_base64_cached()
    sle = None
    if shelf_life_extension is not None:
        qc_d = getattr(shelf_life_extension, "qc_date", None)
        months = getattr(shelf_life_extension, "extension_months", None)
        qname = (getattr(shelf_life_extension, "qc_parameter_name", None) or "").strip()
        qres = getattr(shelf_life_extension, "qc_result_value", None)
        qc_d_s = qc_d.strftime("%B %d, %Y") if qc_d else "—"
        parts = [
            f"Shelf life extension: color / QC value only, as of {qc_d_s}",
            f"(+{months} months)." if months else "",
        ]
        if qname:
            parts.append(f"Parameter: {qname}.")
        if qres is not None:
            parts.append(f"QC result: {float(qres):g}.")
        else:
            parts.append("Prior QC / color value retained; new result not recorded.")
        sle = {
            "banner": " ".join(p for p in parts if p).strip(),
            "qc_date": qc_d_s,
            "months": months,
        }
    return {
        "logo_base64": logo_base64,
        "product_name": _s(product_name),
        "lot_number": _s(lot_number),
        "quantity_display": _s(quantity_display),
        "customer_name": _s(customer_name) or "—",
        "customer_po": _s(customer_po) or "—",
        "manufacture_date": manufacture_date,
        "expiration_date": expiration_date,
        "issue_date": issue_date,
        "test_rows": test_rows,
        "is_example": bool(is_example),
        "shelf_life_extension": sle,
        "batch_lot_trace": _s(batch_lot_trace),
    }


def build_master_coa_context(certificate):
    """Master COA: no customer/PO; quantity from quantity_snapshot or lot.

    Batch lots in a multi-batch campaign: Lot No = campaign code; 8pt footer
    shows the batch lot number. Campaign master COA has no batch footer.
    """
    from .campaign_coa import lot_campaign

    lot = certificate.lot
    item = lot.item
    uom = _s(getattr(item, "unit_of_measure", "") or "lbs")
    if certificate.quantity_snapshot is not None:
        qty = float(certificate.quantity_snapshot)
    else:
        try:
            qty = float(lot.quantity_remaining or lot.quantity or 0)
        except (TypeError, ValueError):
            qty = 0.0
    quantity_display = _format_qty_display(qty, uom)
    manufacture_date, expiration_date = _dates_from_lot(lot)
    issue_dt = certificate.updated_at or certificate.issued_at or timezone.now()
    issue_date = issue_dt.strftime("%B %d, %Y") if issue_dt else ""
    test_rows = _test_rows_from_certificate(certificate)
    latest_sle = None
    try:
        latest_sle = (
            lot.shelf_life_extensions.order_by("-created_at").first()
        )
    except Exception:
        latest_sle = None

    display_lot = lot.lot_number or lot.vendor_lot_number or ""
    batch_trace = ""
    camp = lot_campaign(lot)
    if camp is not None:
        display_lot = camp.campaign_code
        batch_trace = lot.lot_number or str(lot.id)

    return build_coa_template_context(
        product_name=item.name,
        lot_number=display_lot,
        quantity_display=quantity_display,
        customer_name="—",
        customer_po="—",
        manufacture_date=manufacture_date,
        expiration_date=expiration_date,
        issue_date=issue_date,
        test_rows=test_rows,
        shelf_life_extension=latest_sle,
        batch_lot_trace=batch_trace,
    )


def build_customer_copy_coa_context(certificate, copy):
    """Customer-facing COA for one SalesOrderLot allocation."""
    from .campaign_coa import current_campaign_coa, lot_campaign
    from .coa_customer_options import resolve_customer_coa_row_options

    lot = certificate.lot
    item = lot.item
    uom = _s(getattr(item, "unit_of_measure", "") or "lbs")
    quantity_display = _format_qty_display(copy.quantity_snapshot, uom)
    issue_dt = copy.updated_at or copy.created_at or timezone.now()
    issue_date = issue_dt.strftime("%B %d, %Y") if issue_dt else ""

    basis = (getattr(copy, "coa_basis", None) or "batch").strip().lower()
    camp_cert = getattr(copy, "campaign_certificate", None)
    if basis == "campaign" and camp_cert is None:
        camp = lot_campaign(lot)
        if camp is not None:
            camp_cert = current_campaign_coa(camp)

    if basis == "campaign" and camp_cert is not None:
        manufacture_date, expiration_date = _dates_from_campaign_cert(camp_cert)
        test_rows = _test_rows_from_campaign_certificate(
            camp_cert,
            include_qc=bool(getattr(copy, "include_qc_row", True)),
            display_mode=getattr(copy, "result_display_mode", None) or "per_line",
        )
        display_lot = camp_cert.campaign.campaign_code
        batch_trace = lot.lot_number or str(lot.id)
        # Rolled-up campaign qty (multiple batch allocations on one SO) — no single batch footer.
        try:
            so_id = copy.sales_order_lot.sales_order_item.sales_order_id
            from .models import SalesOrderLot
            from .campaign_coa import lot_campaign as _lc

            sibling_n = 0
            for sib in SalesOrderLot.objects.filter(
                sales_order_item__sales_order_id=so_id
            ).select_related("lot"):
                sc = _lc(sib.lot)
                if sc and camp_cert.campaign_id and sc.id == camp_cert.campaign_id:
                    sibling_n += 1
            if sibling_n > 1:
                batch_trace = ""
        except Exception:
            pass
        product_name = camp_cert.campaign.item.name if camp_cert.campaign.item_id else item.name
        sle = (
            camp_cert.campaign.shelf_life_extensions.order_by("-created_at").first()
            if camp_cert.campaign_id
            else None
        )
        return build_coa_template_context(
            product_name=product_name,
            lot_number=display_lot,
            quantity_display=quantity_display,
            customer_name=(copy.customer_name or "").strip() or "—",
            customer_po=(copy.customer_po or "").strip() or "—",
            manufacture_date=manufacture_date,
            expiration_date=expiration_date,
            issue_date=issue_date,
            test_rows=test_rows,
            shelf_life_extension=sle,
            batch_lot_trace=batch_trace,
        )

    manufacture_date, expiration_date = _dates_from_lot(lot)
    opts = resolve_customer_coa_row_options(copy, certificate)
    test_rows = _test_rows_from_certificate(
        certificate,
        include_ids=opts["include_ids"],
        include_qc=opts["include_qc"],
        display_mode=opts["display_mode"],
        line_overrides=opts["line_overrides"],
        spec_overrides=opts.get("spec_overrides") or {},
    )
    display_lot = lot.lot_number or lot.vendor_lot_number or ""
    batch_trace = ""
    camp = lot_campaign(lot)
    if camp is not None:
        display_lot = camp.campaign_code
        batch_trace = lot.lot_number or str(lot.id)
    return build_coa_template_context(
        product_name=item.name,
        lot_number=display_lot,
        quantity_display=quantity_display,
        customer_name=(copy.customer_name or "").strip() or "—",
        customer_po=(copy.customer_po or "").strip() or "—",
        manufacture_date=manufacture_date,
        expiration_date=expiration_date,
        issue_date=issue_date,
        test_rows=test_rows,
        batch_lot_trace=batch_trace,
    )


def _dates_from_campaign_cert(camp_cert):
    mfg = getattr(camp_cert, "manufacture_date", None)
    manufacture_date = mfg.strftime("%B %d, %Y") if mfg else "—"
    ed = getattr(camp_cert, "expiration_date", None)
    d_exp = _to_display_date(ed)
    expiration_date = d_exp.strftime("%B %d, %Y") if d_exp else "—"
    return manufacture_date, expiration_date


def _test_rows_from_campaign_certificate(camp_cert, *, include_qc=True, display_mode="per_line"):
    rows = []
    if include_qc and (camp_cert.qc_parameter_name_snapshot or "").strip():
        qname = camp_cert.qc_parameter_name_snapshot
        spec_bits = []
        if camp_cert.qc_spec_min_snapshot is not None:
            spec_bits.append(f"min {camp_cert.qc_spec_min_snapshot:g}")
        if camp_cert.qc_spec_max_snapshot is not None:
            spec_bits.append(f"max {camp_cert.qc_spec_max_snapshot:g}")
        spec = ", ".join(spec_bits) if spec_bits else "Formula QC"
        if display_mode == "pass_fail":
            if camp_cert.qc_result_pass is True:
                res = "Pass"
            elif camp_cert.qc_result_pass is False:
                res = "Fail"
            else:
                res = "—"
        else:
            res = (
                f"{float(camp_cert.qc_result_value):g}"
                if camp_cert.qc_result_value is not None
                else "—"
            )
        rows.append({"test": qname, "specification": spec, "result": res})
    for lr in camp_cert.line_results.all():
        rows.append(
            {
                "test": lr.test_name,
                "specification": lr.specification_text or "",
                "result": lr.result_text or "",
            }
        )
    return rows


def build_campaign_coa_context(camp_cert):
    """Master campaign COA — campaign code only (no batch-lot footer)."""
    camp = camp_cert.campaign
    item = camp.item
    uom = _s(getattr(item, "unit_of_measure", "") or "lbs") if item else "lbs"
    qty = float(camp_cert.quantity_snapshot or 0)
    quantity_display = _format_qty_display(qty, uom)
    manufacture_date, expiration_date = _dates_from_campaign_cert(camp_cert)
    issue_dt = camp_cert.issued_at or timezone.now()
    issue_date = issue_dt.strftime("%B %d, %Y") if issue_dt else ""
    test_rows = _test_rows_from_campaign_certificate(camp_cert)
    sle = None
    try:
        sle = camp.shelf_life_extensions.order_by("-created_at").first()
    except Exception:
        sle = None
    return build_coa_template_context(
        product_name=item.name if item else camp.campaign_code,
        lot_number=camp.campaign_code,
        quantity_display=quantity_display,
        customer_name="—",
        customer_po="—",
        manufacture_date=manufacture_date,
        expiration_date=expiration_date,
        issue_date=issue_date,
        test_rows=test_rows,
        shelf_life_extension=sle,
        batch_lot_trace="",
    )


def _render_coa_pdf_bytes(context: dict, log_label: str):
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning("COA PDF requires jinja2: %s", e)
        return None

    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "coa"
        if not template_dir.is_dir():
            logger.warning("COA template dir missing: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        template = env.get_template("certificate.html")
        html_string = template.render(**context)
        return html_string_to_pdf_bytes(html_string, log_label=log_label)
    except Exception as e:
        logger.warning("COA PDF failed: %s", e, exc_info=True)
        return None


def generate_lot_coa_pdf_bytes(certificate):
    """Master COA PDF bytes."""
    from .models import LotCoaCertificate

    certificate = (
        LotCoaCertificate.objects.select_related("lot__item")
        .prefetch_related("line_results")
        .get(pk=certificate.pk)
    )
    context = build_master_coa_context(certificate)
    ln = certificate.lot.lot_number or str(certificate.lot_id)
    return _render_coa_pdf_bytes(context, log_label=f"COA master {ln}")


def generate_customer_copy_coa_pdf_bytes(copy):
    """Customer allocation COA PDF bytes."""
    from .models import LotCoaCustomerCopy

    copy = (
        LotCoaCustomerCopy.objects.select_related(
            "certificate",
            "certificate__lot__item",
            "campaign_certificate",
            "campaign_certificate__campaign",
            "campaign_certificate__campaign__item",
            "sales_order_lot__sales_order_item__sales_order__customer",
        )
        .prefetch_related(
            "certificate__line_results",
            "campaign_certificate__line_results",
            "campaign_certificate__campaign__shelf_life_extensions",
        )
        .get(pk=copy.pk)
    )
    cert = copy.certificate
    context = build_customer_copy_coa_context(cert, copy)
    so = copy.sales_order_lot.sales_order_item.sales_order.so_number
    ln = cert.lot.lot_number or str(cert.lot_id)
    return _render_coa_pdf_bytes(context, log_label=f"COA customer {ln} {so}")


def build_example_fps_coa_context(item):
    """
    Sample customer-style COA from FPS ItemCoaTestLine rows (no lot).

    Includes tests marked for customer COA (falls back to all lines if none flagged).
    Result column uses Typical so customers see a representative sheet.
    Uses the family COA template item when packs share one master.
    Prepends formula QC parameter (from default formula on this pack / family).
    """
    from .coa_logic import qc_spec_display
    from .coa_template import coa_test_lines_for_item, family_items, resolve_coa_template_item
    from .formula_resolve import default_formula_for_fg

    template = resolve_coa_template_item(item) or item
    test_rows = []

    # QC from commercial formula (prefer template pack, then requested item, then siblings)
    formula = None
    seen_ids: set[int] = set()
    for candidate in [template, item, *family_items(template or item)]:
        if candidate is None or candidate.id in seen_ids:
            continue
        seen_ids.add(candidate.id)
        f = default_formula_for_fg(candidate.id)
        if f and (f.qc_parameter_name or "").strip():
            formula = f
            break
    if formula is not None:
        qname = (formula.qc_parameter_name or "").strip()
        spec = qc_spec_display(qname, formula.qc_spec_min, formula.qc_spec_max)
        # Spec text already embeds the name for NLT/NMT; keep Test column as parameter name
        test_rows.append(
            {
                "test": _s(qname),
                "specification": _s(spec),
                "result": "—",
            }
        )

    lines = list(coa_test_lines_for_item(template, select_related=None))
    on_coa = [ln for ln in lines if ln.include_on_customer_coa]
    use = on_coa or lines
    for ln in use:
        typical = (ln.typical_result or "").strip()
        test_rows.append(
            {
                "test": _s(ln.test_name),
                "specification": _s(ln.specification_text),
                "result": _s(typical) or "—",
            }
        )
    uom = _s(getattr(template, "unit_of_measure", "") or "lbs")
    issue_date = timezone.localdate().strftime("%B %d, %Y")
    return build_coa_template_context(
        product_name=template.name or template.sku or "Product",
        lot_number="EXAMPLE",
        quantity_display=f"— {uom}".strip(),
        customer_name="(Sample customer)",
        customer_po="EXAMPLE",
        manufacture_date="—",
        expiration_date="—",
        issue_date=issue_date,
        test_rows=test_rows,
        is_example=True,
    )


def generate_example_fps_coa_pdf_bytes(item):
    """Example / typical COA PDF for an FPS (sellable SKU) — for customer requests."""
    context = build_example_fps_coa_context(item)
    sku = getattr(item, "sku", None) or str(item.pk)
    return _render_coa_pdf_bytes(context, log_label=f"COA example {sku}")


def backfill_lot_expiration_from_shelf_life(lot) -> bool:
    """When lot.expiration_date is unset, set it to manufacture + formula shelf life.

    Returns True if the lot was updated. Safe no-op when dates or shelf life missing.
    """
    if lot is None or getattr(lot, "expiration_date", None) is not None:
        return False
    from .formula_resolve import formula_for_lot
    from .views import _expiration_datetime_for_fg_output

    base = getattr(lot, "manufacture_date", None)
    if base is None:
        try:
            from .models import ProductionBatchOutput

            base = (
                ProductionBatchOutput.objects.filter(lot_id=lot.pk)
                .exclude(batch__closed_date__isnull=True)
                .order_by("-batch__closed_date")
                .values_list("batch__closed_date", flat=True)
                .first()
            ) or getattr(lot, "received_date", None)
        except Exception:
            base = getattr(lot, "received_date", None)
    if base is None:
        return False
    formula = formula_for_lot(lot)
    computed = _expiration_datetime_for_fg_output(lot.item, base, formula=formula)
    if computed is None:
        return False
    lot.expiration_date = computed
    if getattr(lot, "manufacture_date", None) is None:
        lot.manufacture_date = base
        lot.save(update_fields=["manufacture_date", "expiration_date"])
    else:
        lot.save(update_fields=["expiration_date"])
    return True


def save_coa_pdf_to_certificate(certificate) -> bool:
    """Generate master PDF and save to certificate.coa_pdf."""
    from django.core.files.base import ContentFile

    lot = certificate.lot
    try:
        backfill_lot_expiration_from_shelf_life(lot)
        if lot is not None:
            lot.refresh_from_db()
    except Exception:
        logger.exception("backfill_lot_expiration_from_shelf_life failed for lot %s", getattr(lot, "pk", None))

    pdf = generate_lot_coa_pdf_bytes(certificate)
    if not pdf:
        return False
    lot = certificate.lot
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (lot.lot_number or str(lot.id)))
    fname = f"COA_master_{safe}_{timezone.now().strftime('%Y%m%d')}.pdf"
    certificate.coa_pdf.save(fname, ContentFile(pdf), save=False)
    certificate.save(update_fields=["coa_pdf", "updated_at"])
    return True


def generate_campaign_coa_pdf_bytes(camp_cert):
    from .models import CampaignCoaCertificate

    camp_cert = (
        CampaignCoaCertificate.objects.select_related("campaign", "campaign__item")
        .prefetch_related("line_results", "campaign__shelf_life_extensions")
        .get(pk=camp_cert.pk)
    )
    context = build_campaign_coa_context(camp_cert)
    code = camp_cert.campaign.campaign_code
    return _render_coa_pdf_bytes(context, log_label=f"COA campaign {code} v{camp_cert.version}")


def save_campaign_coa_pdf(camp_cert) -> bool:
    from django.core.files.base import ContentFile

    pdf = generate_campaign_coa_pdf_bytes(camp_cert)
    if not pdf:
        return False
    code = camp_cert.campaign.campaign_code
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in code)
    fname = f"COA_campaign_{safe}_v{camp_cert.version}_{timezone.now().strftime('%Y%m%d')}.pdf"
    camp_cert.coa_pdf.save(fname, ContentFile(pdf), save=False)
    camp_cert.save(update_fields=["coa_pdf"])
    return True


def refresh_lot_coa_pdf_if_exists(lot) -> bool:
    """Regenerate stored master COA PDF when lot data (e.g. expiration) changes."""
    from .models import LotCoaCertificate

    cert = LotCoaCertificate.objects.filter(lot_id=lot.pk).first()
    if not cert:
        return False
    return save_coa_pdf_to_certificate(cert)


def refresh_all_coa_pdfs_for_lot(lot):
    """Regenerate master COA for this lot. Customer copies with PDFs are immutable."""
    refresh_lot_coa_pdf_if_exists(lot)


def save_customer_copy_coa_pdf(copy) -> bool:
    """Generate customer COA PDF and save to copy.coa_pdf.

    Never overwrites an existing PDF (issued copies are immutable).
    """
    from django.core.files.base import ContentFile

    if copy.coa_pdf:
        return False
    pdf = generate_customer_copy_coa_pdf_bytes(copy)
    if not pdf:
        return False
    cert = copy.certificate
    lot = cert.lot
    so = copy.sales_order_lot.sales_order_item.sales_order.so_number
    safe_lot = "".join(c if c.isalnum() or c in "-_" else "_" for c in (lot.lot_number or str(lot.id)))
    safe_so = "".join(c if c.isalnum() or c in "-_" else "_" for c in so)
    fname = f"COA_{safe_lot}_{safe_so}_{copy.pk}.pdf"
    copy.coa_pdf.save(fname, ContentFile(pdf), save=False)
    copy.save(update_fields=["coa_pdf", "updated_at"])
    return True
