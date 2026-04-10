"""
Sales order confirmation PDF: Jinja2 HTML template → xhtml2pdf (same flow as PO / invoice).
"""
from pathlib import Path
import logging

from .html_pdf_common import html_string_to_pdf_bytes
from .pdf_generator import get_batch_ticket_logo_base64_cached

logger = logging.getLogger(__name__)


def _build_sales_order_context(sales_order):
    """Context aligned with pdf_generator.generate_sales_order_pdf."""
    logo_base64 = get_batch_ticket_logo_base64_cached()

    order_date = sales_order.order_date.strftime("%Y-%m-%d") if getattr(sales_order, "order_date", None) else "—"
    exp_ship = sales_order.expected_ship_date.strftime("%Y-%m-%d") if getattr(sales_order, "expected_ship_date", None) else "N/A"
    status = (getattr(sales_order, "status", None) or "draft").upper()

    rows = []
    for item in sales_order.items.select_related("item").all():
        it = item.item
        sku = (it.sku if it else "") or "N/A"
        name = (it.name if it else "") or "N/A"
        qty = getattr(item, "quantity_ordered", 0) or 0
        up = getattr(item, "unit_price", None)
        line_total = qty * (up or 0)
        uom = (getattr(it, "unit_of_measure", None) or "") if it else ""
        rows.append(
            {
                "sku": sku,
                "description": name,
                "qty": f"{qty:,.2f}" + (f" {uom}".strip() if uom else ""),
                "unit_price": f"${up:,.2f}" if up is not None else "$0.00",
                "line_total": f"${line_total:,.2f}",
            }
        )
    if not rows:
        rows = [
            {
                "sku": "—",
                "description": "—",
                "qty": "—",
                "unit_price": "—",
                "line_total": "—",
            }
        ]

    cust_po = ""
    if getattr(sales_order, "customer_reference_number", None):
        cust_po = (sales_order.customer_reference_number or "").strip()

    return {
        "so_number": (sales_order.so_number or "").strip() or "—",
        "order_date": order_date,
        "expected_ship_date": exp_ship,
        "customer_name": (sales_order.customer_name or "").strip() or "—",
        "status": status,
        "customer_po": cust_po or None,
        "line_items": rows,
        "logo_base64": logo_base64,
    }


def generate_sales_order_pdf_from_html(sales_order):
    """
    Render sales order confirmation HTML, convert with xhtml2pdf (shared worker).
    Returns PDF bytes or None on failure.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning("Sales order HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None

    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "sales_order"
        if not template_dir.is_dir():
            logger.warning("Sales order template dir not found: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("sales_order_confirmation.html")
        context = _build_sales_order_context(sales_order)
        html_string = template.render(**context)

        so = (getattr(sales_order, "so_number", None) or "") or ""
        out = html_string_to_pdf_bytes(html_string, log_label=f"Sales order {so}".strip() or "Sales order PDF")
        if out:
            logger.info("Sales order PDF: HTML path succeeded, size=%s", len(out))
        return out
    except Exception as e:
        logger.warning("Sales order HTML→PDF failed: %s", e, exc_info=True)
        return None
