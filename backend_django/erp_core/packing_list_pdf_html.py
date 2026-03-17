"""
Packing list PDF via Jinja2 HTML template → xhtml2pdf.
Same flow as invoice_pdf_html: build context from sales order, render HTML, convert to PDF.
"""
from pathlib import Path
import base64
import logging
from io import BytesIO
from django.utils import timezone

logger = logging.getLogger(__name__)


def _build_packing_list_context(sales_order):
    """Build template context from SalesOrder. Matches data used by the template-fill packing list."""
    # Ship to
    ship_to_lines = []
    if getattr(sales_order, 'ship_to_location', None) and sales_order.ship_to_location:
        loc = sales_order.ship_to_location
        if loc.location_name:
            ship_to_lines.append(loc.location_name)
        if loc.contact_name:
            ship_to_lines.append(loc.contact_name)
        if loc.address:
            ship_to_lines.append(loc.address)
        csz = [x for x in [loc.city, loc.state, loc.zip_code] if x]
        if csz:
            ship_to_lines.append(', '.join(csz))
        if loc.country:
            ship_to_lines.append(loc.country)
    else:
        if sales_order.customer_name:
            ship_to_lines.append(sales_order.customer_name)
        if sales_order.customer_address:
            ship_to_lines.append(sales_order.customer_address)
        csz = [x for x in [sales_order.customer_city, sales_order.customer_state, sales_order.customer_zip] if x]
        if csz:
            ship_to_lines.append(', '.join(csz))
        if sales_order.customer_country:
            ship_to_lines.append(sales_order.customer_country)
    ship_to_text = '\n'.join(ship_to_lines) if ship_to_lines else (sales_order.customer_name or '—')

    # Bill to
    bill_to_lines = []
    if getattr(sales_order, 'customer', None) and sales_order.customer:
        c = sales_order.customer
        if c.name:
            bill_to_lines.append(c.name)
        if c.address:
            bill_to_lines.append(c.address)
        csz = [x for x in [c.city, c.state, c.zip_code] if x]
        if csz:
            bill_to_lines.append(', '.join(csz))
        if c.country:
            bill_to_lines.append(c.country)
    else:
        bill_to_lines.append(sales_order.customer_name or '—')
        if sales_order.customer_address:
            bill_to_lines.append(sales_order.customer_address)
        csz = [x for x in [sales_order.customer_city, sales_order.customer_state, sales_order.customer_zip] if x]
        if csz:
            bill_to_lines.append(', '.join(csz))
        if sales_order.customer_country:
            bill_to_lines.append(sales_order.customer_country)
    bill_to_text = '\n'.join(bill_to_lines) if bill_to_lines else (sales_order.customer_name or '—')

    pack_date = timezone.now().date()
    date_str = pack_date.strftime('%Y-%m-%d')
    order_date_str = sales_order.order_date.strftime('%Y-%m-%d') if sales_order.order_date else ''
    ship_date_dt = sales_order.actual_ship_date or sales_order.expected_ship_date
    ship_date_str = ship_date_dt.strftime('%Y-%m-%d') if ship_date_dt else ''
    po_ref = (sales_order.customer_reference_number or '').strip()
    so_number = (sales_order.so_number or '').strip()
    po_so_str = f"{po_ref} / {so_number}" if po_ref and so_number else (so_number or po_ref or '—')

    latest_shipment = sales_order.shipments.order_by('-created_at').first()
    dimensions = ''
    pieces = ''
    if latest_shipment:
        dimensions = (latest_shipment.dimensions or '').strip()
        if latest_shipment.pieces is not None:
            pieces = str(latest_shipment.pieces)

    # Line items
    items = []
    for item in sales_order.items.select_related('item').all()[:50]:
        it = getattr(item, 'item', None)
        sku = (it.sku if it else '') or ''
        name = (it.name if it else '') or ''
        qty = getattr(item, 'quantity_ordered', 0) or 0
        uom = (it.unit_of_measure if it else '') or ''
        qty_display = f"{round(qty, 2):.2f}".rstrip('0').rstrip('.') if isinstance(qty, (int, float)) else str(qty)
        qty_with_uom = f"{qty_display} {uom}".strip() if uom else qty_display
        items.append({
            'sku': sku[:40],
            'description': (name or sku)[:50],
            'quantity': qty_with_uom[:20],
        })
    if not items:
        items = [{'sku': '—', 'description': '—', 'quantity': '—'}]

    logo_base64 = ''
    try:
        from .pdf_generator import get_batch_ticket_logo_path
        logo_path = get_batch_ticket_logo_path()
        if logo_path and Path(logo_path).exists():
            with open(logo_path, 'rb') as f:
                logo_base64 = base64.b64encode(f.read()).decode('ascii')
    except Exception:
        pass

    return {
        'so_number': so_number,
        'ship_to_text': ship_to_text,
        'bill_to_text': bill_to_text,
        'date_str': date_str,
        'order_date_str': order_date_str or '—',
        'ship_date_str': ship_date_str or '—',
        'po_ref': po_ref or '—',
        'po_so_str': po_so_str,
        'dimensions': dimensions or '—',
        'pieces': pieces or '—',
        'line_items': items,
        'logo_base64': logo_base64,
    }


def generate_packing_list_pdf_from_html(sales_order):
    """
    Render packing list HTML template with Jinja2, convert to PDF with xhtml2pdf.
    Returns PDF bytes or None on failure. Same flow as generate_invoice_pdf_from_html.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from xhtml2pdf import pisa
    except ImportError as e:
        logger.warning("Packing list HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None

    context = _build_packing_list_context(sales_order)
    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "packing_list"
        if not template_dir.is_dir():
            logger.warning("Packing list template dir not found: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("packing_list.html")
        html_string = template.render(**context)

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        if getattr(result, "err", 1) != 0:
            logger.warning("Packing list xhtml2pdf errors: err=%s", getattr(result, "err", None))
            return None
        pdf_buffer.seek(0)
        out = pdf_buffer.getvalue()
        logger.info("Packing list PDF: HTML path succeeded, size=%s", len(out))
        return out
    except Exception as e:
        logger.warning("Packing list HTML→PDF failed: %s", e, exc_info=True)
        return None


def _build_packing_list_context_from_shipment(shipment):
    """Build template context for one shipment (one packing list per release)."""
    sales_order = shipment.sales_order
    base = _build_packing_list_context(sales_order)
    pack_date = timezone.now().date()
    base['date_str'] = pack_date.strftime('%Y-%m-%d')
    if shipment.ship_date:
        base['ship_date_str'] = shipment.ship_date.strftime('%Y-%m-%d')
    base['dimensions'] = (shipment.dimensions or '').strip() or '—'
    base['pieces'] = str(shipment.pieces) if shipment.pieces is not None else '—'
    base['tracking_number'] = (shipment.tracking_number or '').strip() or '—'
    si_items = list(shipment.items.select_related('sales_order_item__item').all())
    if si_items:
        items = []
        for si in si_items[:50]:
            so_item = si.sales_order_item
            it = getattr(so_item, 'item', None) if so_item else None
            sku = (it.sku if it else '') or ''
            name = (it.name if it else '') or ''
            qty = getattr(si, 'quantity_shipped', 0) or 0
            uom = (it.unit_of_measure if it else '') or ''
            qty_display = f"{round(qty, 2):.2f}".rstrip('0').rstrip('.') if isinstance(qty, (int, float)) else str(qty)
            qty_with_uom = f"{qty_display} {uom}".strip() if uom else qty_display
            items.append({'sku': sku[:40], 'description': (name or sku)[:50], 'quantity': qty_with_uom[:20]})
        base['line_items'] = items if items else base['line_items']
    return base


def generate_packing_list_pdf_from_shipment(shipment):
    """Generate packing list PDF for a single shipment (one per release)."""
    try:
        from jinja2 import Environment, FileSystemLoader
        from xhtml2pdf import pisa
    except ImportError as e:
        logger.warning("Packing list HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None
    context = _build_packing_list_context_from_shipment(shipment)
    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "packing_list"
        if not template_dir.is_dir():
            return None
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("packing_list.html")
        html_string = template.render(**context)
        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        if getattr(result, "err", 1) != 0:
            return None
        pdf_buffer.seek(0)
        out = pdf_buffer.getvalue()
        logger.info("Packing list PDF (shipment %s): size=%s", shipment.id, len(out))
        return out
    except Exception as e:
        logger.warning("Packing list from shipment failed: %s", e, exc_info=True)
        return None
