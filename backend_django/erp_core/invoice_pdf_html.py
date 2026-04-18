"""
Invoice PDF via Jinja2 HTML template → xhtml2pdf.
Layout matches current ReportLab invoice: header, BILL TO/SHIP TO, comments, ref row, line items, totals, footer.
"""
from pathlib import Path
import logging

from .html_pdf_common import html_string_to_pdf_bytes
from .invoice_helpers import (
    format_invoice_quantity_display,
    resolve_payment_terms_for_invoice,
    unit_of_measure_for_invoice_line,
)
from .pdf_generator import get_batch_ticket_logo_base64_cached

logger = logging.getLogger(__name__)


def _build_invoice_context(invoice):
    """Build template context from Invoice. Matches data used by generate_invoice_pdf in pdf_generator."""
    bill_lines: list = []
    ship_lines: list = []
    try:
        from .pdf_generator import _invoice_bill_to, _invoice_ship_to

        bill_lines, _ = _invoice_bill_to(invoice)
    except Exception as e:
        logger.warning('Invoice PDF: bill-to block failed: %s', e, exc_info=True)
    payment_terms = resolve_payment_terms_for_invoice(invoice)
    try:
        from .pdf_generator import _invoice_ship_to

        ship_lines = _invoice_ship_to(invoice)
    except Exception as e:
        logger.warning('Invoice PDF: ship-to block failed: %s', e, exc_info=True)
    bill_text = '<br/>'.join(bill_lines) if bill_lines else '—'
    ship_text = '<br/>'.join(ship_lines) if ship_lines else '—'

    so = getattr(invoice, 'sales_order', None)
    cust_ref = (getattr(so, 'customer_reference_number', None) or '').strip() if so else ''
    po_num = cust_ref
    so_num = (getattr(so, 'so_number', None) or '').strip() if so else ''
    carrier = (getattr(so, 'carrier', None) or '').strip() if so else ''
    track = (getattr(so, 'tracking_number', None) or '').strip() if so else ''
    shipped_via = ' '.join(filter(None, [carrier, track])).strip() or '—'
    so_notes = (getattr(so, 'notes', None) or '').strip() if so else ''
    inv_notes = (getattr(invoice, 'notes', None) or '').strip()
    comments_text = ' '.join(filter(None, [so_notes, inv_notes])).strip()

    inv_num = (getattr(invoice, 'invoice_number', None) or '').strip()
    inv_date = invoice.invoice_date.strftime('%m/%d/%Y') if getattr(invoice, 'invoice_date', None) else ''

    items = []
    try:
        for it in invoice.items.select_related('item', 'sales_order_item__item').all():
            desc = (getattr(it, 'description', None) or '').strip()
            if not desc and getattr(it, 'item', None):
                desc = (getattr(it.item, 'name', None) or getattr(it.item, 'sku', None) or '').strip()
            qty = getattr(it, 'quantity', None)
            uom = unit_of_measure_for_invoice_line(it)
            up = getattr(it, 'unit_price', None)
            total = getattr(it, 'total', None)
            if total is None and qty is not None and up is not None:
                total = qty * up
            items.append({
                'qty': format_invoice_quantity_display(qty, uom),
                'description': desc or '—',
                'unit_price': f"${up:,.2f}" if up is not None else '—',
                'total': f"${total:,.2f}" if total is not None else '—',
            })
    except Exception:
        pass
    if not items:
        items = [{'qty': '—', 'description': '—', 'unit_price': '—', 'total': '—'}]

    subtotal = getattr(invoice, 'subtotal', None)
    if subtotal is None and items:
        try:
            subtotal = sum((getattr(it, 'total', None) or 0) for it in invoice.items.all())
        except Exception:
            subtotal = 0.0
    subtotal = float(subtotal or 0.0)
    tax = float(getattr(invoice, 'tax', None) or 0.0)
    freight = float(getattr(invoice, 'freight', None) or 0.0)
    grand = getattr(invoice, 'grand_total', None)
    if grand is None:
        grand = subtotal + tax + freight
    grand = float(grand)

    logo_base64 = get_batch_ticket_logo_base64_cached()

    return {
        'invoice_number': inv_num,
        'invoice_date': inv_date,
        'bill_to_html': bill_text,
        'ship_to_html': ship_text,
        'comments_text': comments_text.replace('&', '&amp;'),
        'cust_ref': cust_ref or '—',
        'po_num': po_num or '—',
        'so_num': so_num or '—',
        'shipped_via': shipped_via,
        'payment_terms': payment_terms or '—',
        'line_items': items,
        'subtotal': f"${subtotal:,.2f}",
        'tax': f"${tax:,.2f}",
        'shipping': f"${freight:,.2f}",
        'total_due': f"${grand:,.2f}",
        'logo_base64': logo_base64,
    }


def generate_invoice_pdf_from_html(invoice):
    """
    Render invoice HTML template with Jinja2, convert to PDF with xhtml2pdf.
    Returns PDF bytes or None on failure.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning("Invoice HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None

    context = _build_invoice_context(invoice)
    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "invoice"
        if not template_dir.is_dir():
            logger.warning("Invoice template dir not found: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("invoice.html")
        html_string = template.render(**context)

        inv = (getattr(invoice, "invoice_number", None) or "") or ""
        out = html_string_to_pdf_bytes(html_string, log_label=f"Invoice {inv}".strip() or "Invoice PDF")
        if out:
            logger.info("Invoice PDF: HTML path succeeded, size=%s", len(out))
        return out
    except Exception as e:
        logger.warning("Invoice HTML→PDF failed: %s", e, exc_info=True)
        return None
