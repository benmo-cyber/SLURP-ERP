"""
Sales order pick list PDF: one row per allocated lot (SKU, description, WWI lot #, qty).
Uses same header/address pattern as packing_list_pdf_html.
"""
from pathlib import Path
import logging

from .html_pdf_common import html_string_to_pdf_bytes

logger = logging.getLogger(__name__)


def _format_pick_quantity_for_display(qty, uom: str) -> str:
    """
    Stable, human-readable qty for pick lists — no float noise (e.g. 499.999999 → 500).
    Mass UoM: 2 decimal places; ea: integer when whole, else up to 5 dp.
    """
    u = (uom or "").strip().lower()
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return str(qty)
    if u == "ea":
        rq = round(q, 5)
        if abs(rq - round(rq)) < 1e-9:
            return str(int(round(rq)))
        s = f"{rq:.5f}".rstrip("0").rstrip(".")
        return s if s else "0"
    # lbs, kg, and everything else: 2 dp (matches sales / inventory display)
    rq = round(q, 2)
    s = f"{rq:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def pick_list_has_rows(sales_order) -> bool:
    """True if at least one line has a positive allocation on a lot."""
    for line in sales_order.items.all():
        for al in line.allocated_lots.all():
            if (al.quantity_allocated or 0) > 0 and al.lot_id:
                return True
    return False


def _pick_list_rows(sales_order):
    rows = []
    for so_item in sales_order.items.all().order_by('id'):
        it = getattr(so_item, 'item', None)
        if not it:
            continue
        sku = ((it.sku or '') or '')[:48]
        name = ((it.name or '') or '')[:120]
        uom = (getattr(it, 'unit_of_measure', None) or '').strip()
        for al in so_item.allocated_lots.all().order_by('id'):
            qty = float(al.quantity_allocated or 0)
            if qty <= 0:
                continue
            lot = al.lot
            if not lot:
                continue
            ln = (lot.lot_number or lot.vendor_lot_number or str(lot.pk)).strip()[:40]
            qty_s = _format_pick_quantity_for_display(qty, uom)
            qty_uom = f"{qty_s} {uom}".strip() if uom else qty_s
            rows.append(
                {
                    'sku': sku,
                    'description': name,
                    'lot_number': ln,
                    'quantity': qty_uom[:36],
                }
            )
    return rows


def build_pick_list_context(sales_order):
    """Template context; reuses packing list address builder then replaces line items."""
    from .packing_list_pdf_html import _build_packing_list_context

    ctx = _build_packing_list_context(sales_order)
    ctx['line_items'] = _pick_list_rows(sales_order)
    # Pick list is pre-shipment: omit checkout-only fields from the packing-list template clone.
    ctx['carrier'] = '—'
    ctx['tracking_number'] = '—'
    ctx['pieces'] = '—'
    ctx['dimensions'] = '—'
    ctx['piece_dimension_rows'] = []
    return ctx


def generate_pick_list_pdf_from_html(sales_order):
    """Render pick_list.html → PDF bytes."""
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning('Pick list HTML→PDF requires jinja2: %s', e)
        return None

    if not pick_list_has_rows(sales_order):
        return None

    context = build_pick_list_context(sales_order)
    try:
        template_dir = Path(__file__).resolve().parent / 'templates' / 'sales_order'
        if not template_dir.is_dir():
            logger.warning('Pick list template dir not found: %s', template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template('pick_list.html')
        html_string = template.render(**context)
        so = (getattr(sales_order, 'so_number', None) or '') or ''
        out = html_string_to_pdf_bytes(html_string, log_label=f'Pick list {so}'.strip() or 'Pick list PDF')
        if out:
            logger.info('Pick list PDF: size=%s', len(out))
        return out
    except Exception as e:
        logger.warning('Pick list HTML→PDF failed: %s', e, exc_info=True)
        return None
