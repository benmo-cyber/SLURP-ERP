"""
Purchase Order PDF via Jinja2 HTML template → xhtml2pdf (pure Python, no system libs).
Build context from PurchaseOrder, render HTML, convert to PDF. No placeholder redaction.
"""
from pathlib import Path
import base64
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# Dark blue and light blue from PO template
PO_HEADING_BLUE = "#1e3a5f"
PO_HEADER_BG = "#c5d4e8"
PO_STATUS_BG = "#d4e0ed"
PO_TOTAL_BG = "#1e3a5f"


def _build_po_context(purchase_order):
    """Build template context from PurchaseOrder. All calculations done here."""
    order_date = purchase_order.order_date.strftime("%b %d, %Y") if getattr(purchase_order, "order_date", None) else ""
    delivery = purchase_order.expected_delivery_date or getattr(purchase_order, "required_date", None)
    delivery_date = delivery.strftime("%b %d, %Y") if delivery else ""

    payment_terms = ""
    try:
        from .models import Vendor
        v = Vendor.objects.filter(name=purchase_order.vendor_customer_name).first()
        if v and getattr(v, "payment_terms", None):
            payment_terms = (v.payment_terms or "").strip()
    except Exception:
        pass

    ship_via = (getattr(purchase_order, "shipping_method", None) or getattr(purchase_order, "carrier", None) or "").strip()
    _rb = getattr(purchase_order, "requested_by", None)
    requested_by = str(_rb) if _rb else ""
    _st = getattr(purchase_order, "status", None) or "draft"
    status = str(_st).capitalize()

    vendor_name = (purchase_order.vendor_customer_name or "").strip()
    vendor_addr1 = (purchase_order.vendor_address or "").strip()
    vendor_addr2 = ", ".join(filter(None, [purchase_order.vendor_city, purchase_order.vendor_state, purchase_order.vendor_zip]))

    bill_to_name = "Wildwood Ingredients, LLC"
    bill_to_addr1 = "6431 Michels Drive"
    bill_to_addr2 = "Washington, MO 63090"

    ship_to_name = (purchase_order.ship_to_name or "").strip()
    ship_to_addr1 = (purchase_order.ship_to_address or "").strip()
    ship_to_addr2 = ", ".join(filter(None, [purchase_order.ship_to_city, purchase_order.ship_to_state, purchase_order.ship_to_zip]))

    notes = (getattr(purchase_order, "notes", None) or "").strip()

    line_items = []
    for idx, po_item in enumerate(purchase_order.items.select_related("item").all(), 1):
        item = po_item.item
        desc = (item.name if item else (po_item.notes or "")) or ""
        uom = (getattr(item, "unit_of_measure", None) if item else None) or "lbs"
        qty = po_item.quantity_ordered
        up = po_item.unit_price or 0
        line_total = qty * up
        # PO line items don't have tax % in model; show — unless we add the field later
        tax_pct_str = "—"
        line_items.append({
            "num": idx,
            "description": desc[:60],
            "qty": f"{qty:,.2f}",
            "unit": uom,
            "unit_price": f"${up:,.2f}",
            "tax_pct": tax_pct_str,
            "line_total": f"${line_total:,.2f}",
        })

    subtotal = sum((pi.quantity_ordered * (pi.unit_price or 0)) for pi in purchase_order.items.all())
    subtotal = round(subtotal, 2)
    discount = float(getattr(purchase_order, "discount", 0) or 0)
    shipping_cost = float(getattr(purchase_order, "shipping_cost", 0) or 0)
    total = round(subtotal - discount + shipping_cost, 2)

    logo_base64 = ""
    try:
        from .pdf_generator import get_batch_ticket_logo_path
        logo_path = get_batch_ticket_logo_path()
        if logo_path and Path(logo_path).exists():
            with open(logo_path, "rb") as f:
                logo_base64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        pass

    return {
        "po_number": purchase_order.po_number or "",
        "po_date": order_date,
        "delivery_date": delivery_date,
        "status": status,
        "requested_by": requested_by,
        "payment_terms": payment_terms,
        "ship_via": ship_via,
        "vendor_name": vendor_name,
        "vendor_addr1": vendor_addr1,
        "vendor_addr2": vendor_addr2,
        "bill_to_name": bill_to_name,
        "bill_to_addr1": bill_to_addr1,
        "bill_to_addr2": bill_to_addr2,
        "ship_to_name": ship_to_name,
        "ship_to_addr1": ship_to_addr1,
        "ship_to_addr2": ship_to_addr2,
        "notes": notes or "",
        "line_items": line_items,
        "subtotal": f"${subtotal:,.2f}",
        "shipping": f"${shipping_cost:,.2f}",
        "discount": f"-${discount:,.2f}",
        "total": f"${total:,.2f}",
        "logo_base64": logo_base64,
    }


def generate_po_pdf_from_html(purchase_order):
    """
    Render PO HTML template with Jinja2, convert to PDF with xhtml2pdf (pure Python).
    Returns PDF bytes or None on failure.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from xhtml2pdf import pisa
    except ImportError as e:
        logger.warning("PO HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None

    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "po"
        if not template_dir.is_dir():
            logger.warning("PO template dir not found: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("purchase_order.html")
        context = _build_po_context(purchase_order)
        html_string = template.render(**context)

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        # pisa returns a context object; .err is the error count (0 = success)
        err = getattr(result, "err", 1)
        if err != 0:
            logger.warning(
                "PO xhtml2pdf reported errors: err=%s, log=%s",
                err,
                getattr(result, "log", None),
            )
            return None
        pdf_buffer.seek(0)
        out = pdf_buffer.getvalue()
        logger.info("PO PDF: HTML path succeeded, size=%s", len(out))
        return out
    except Exception as e:
        logger.warning("PO HTML→PDF failed: %s", e, exc_info=True)
        return None
