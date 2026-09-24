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
    return str(val)


def _format_qty_display(qty, uom: str) -> str:
    try:
        q = float(qty)
        qty_s = f"{q:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        qty_s = _s(qty)
    return f"{qty_s} {(uom or 'lbs')}".strip()


def _test_rows_from_certificate(
    certificate,
    *,
    include_ids=None,
    include_qc: bool = True,
    display_mode: str = "actual",
    line_overrides: dict | None = None,
):
    """
    Build Test | Specification | Result rows for a COA PDF.

    Master path: include_ids=None, include_qc=True, display_mode='actual'.
    Customer path: filter by include_ids / include_qc; display_mode may be
    actual | pass_fail | per_line (with line_overrides).
    """
    from .coa_customer_options import _pass_fail_label
    from .coa_logic import qc_spec_display

    mode = (display_mode or "actual").strip().lower()
    overrides = line_overrides or {}
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
            res = _pass_fail_label(lr.passes)
        else:
            res = _s(lr.result_text)
        test_rows.append(
            {
                "test": _s(lr.test_name),
                "specification": _s(lr.specification_text),
                "result": res,
            }
        )
    return test_rows


def _dates_from_lot(lot):
    """Manuf. / exp from the lot row (same fields as inventory). Calendar only; shows — when unset."""

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

    md = getattr(lot, "manufacture_date", None)
    d = _to_display_date(md)
    manufacture_date = d.strftime("%B %d, %Y") if d else "—"

    ed = getattr(lot, "expiration_date", None)
    d = _to_display_date(ed)
    expiration_date = d.strftime("%B %d, %Y") if d else "—"

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
):
    logo_base64 = get_batch_ticket_logo_base64_cached()
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
    }


def build_master_coa_context(certificate):
    """Master COA: no customer/PO; quantity from quantity_snapshot or lot."""
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
    issue_dt = certificate.issued_at or timezone.now()
    issue_date = issue_dt.strftime("%B %d, %Y") if issue_dt else ""
    test_rows = _test_rows_from_certificate(certificate)
    return build_coa_template_context(
        product_name=item.name,
        lot_number=lot.lot_number or lot.vendor_lot_number or "",
        quantity_display=quantity_display,
        customer_name="—",
        customer_po="—",
        manufacture_date=manufacture_date,
        expiration_date=expiration_date,
        issue_date=issue_date,
        test_rows=test_rows,
    )


def build_customer_copy_coa_context(certificate, copy):
    """Customer-facing COA for one SalesOrderLot allocation."""
    from .coa_customer_options import resolve_customer_coa_row_options

    lot = certificate.lot
    item = lot.item
    uom = _s(getattr(item, "unit_of_measure", "") or "lbs")
    quantity_display = _format_qty_display(copy.quantity_snapshot, uom)
    manufacture_date, expiration_date = _dates_from_lot(lot)
    issue_dt = copy.updated_at or copy.created_at or timezone.now()
    issue_date = issue_dt.strftime("%B %d, %Y") if issue_dt else ""
    opts = resolve_customer_coa_row_options(copy, certificate)
    test_rows = _test_rows_from_certificate(
        certificate,
        include_ids=opts["include_ids"],
        include_qc=opts["include_qc"],
        display_mode=opts["display_mode"],
        line_overrides=opts["line_overrides"],
    )
    return build_coa_template_context(
        product_name=item.name,
        lot_number=lot.lot_number or lot.vendor_lot_number or "",
        quantity_display=quantity_display,
        customer_name=(copy.customer_name or "").strip() or "—",
        customer_po=(copy.customer_po or "").strip() or "—",
        manufacture_date=manufacture_date,
        expiration_date=expiration_date,
        issue_date=issue_date,
        test_rows=test_rows,
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
            "sales_order_lot__sales_order_item__sales_order__customer",
        )
        .prefetch_related("certificate__line_results")
        .get(pk=copy.pk)
    )
    cert = copy.certificate
    context = build_customer_copy_coa_context(cert, copy)
    so = copy.sales_order_lot.sales_order_item.sales_order.so_number
    ln = cert.lot.lot_number or str(cert.lot_id)
    return _render_coa_pdf_bytes(context, log_label=f"COA customer {ln} {so}")


def save_coa_pdf_to_certificate(certificate) -> bool:
    """Generate master PDF and save to certificate.coa_pdf."""
    from django.core.files.base import ContentFile

    pdf = generate_lot_coa_pdf_bytes(certificate)
    if not pdf:
        return False
    lot = certificate.lot
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (lot.lot_number or str(lot.id)))
    fname = f"COA_master_{safe}_{timezone.now().strftime('%Y%m%d')}.pdf"
    certificate.coa_pdf.save(fname, ContentFile(pdf), save=False)
    certificate.save(update_fields=["coa_pdf", "updated_at"])
    return True


def refresh_lot_coa_pdf_if_exists(lot) -> bool:
    """Regenerate stored master COA PDF when lot data (e.g. expiration) changes."""
    from .models import LotCoaCertificate

    cert = LotCoaCertificate.objects.filter(lot_id=lot.pk).first()
    if not cert:
        return False
    return save_coa_pdf_to_certificate(cert)


def refresh_all_coa_pdfs_for_lot(lot):
    """Regenerate master COA and any customer allocation COAs for this lot (e.g. after expiration change)."""
    from .models import LotCoaCustomerCopy

    refresh_lot_coa_pdf_if_exists(lot)
    for cc in LotCoaCustomerCopy.objects.filter(certificate__lot_id=lot.pk):
        save_customer_copy_coa_pdf(cc)


def save_customer_copy_coa_pdf(copy) -> bool:
    """Generate customer COA PDF and save to copy.coa_pdf."""
    from django.core.files.base import ContentFile

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
