"""
Packing list PDF via Jinja2 HTML template → xhtml2pdf.
Same flow as invoice_pdf_html: build context from sales order, render HTML, convert to PDF.
"""
from pathlib import Path
import logging
from django.utils import timezone

from .html_pdf_common import html_string_to_pdf_bytes
from .pdf_generator import get_batch_ticket_logo_base64_cached

logger = logging.getLogger(__name__)


def _split_address_line_for_display(s):
    """
    Turn one stored string into one or more display lines.
    Splits on newlines; for long comma-separated text, splits on commas only when there are 3+ commas
    (so "City, ST, ZIP" stays on one line under Ship To / Bill To).
    """
    s = (s or "").strip()
    if not s:
        return []
    if "\n" in s:
        parts = []
        for line in s.split("\n"):
            parts.extend(_split_address_line_for_display(line))
        return parts
    # Keep "City, ST, ZIP" on one line (2 commas). Only split very long / many-part lines.
    if "," in s and (len(s) > 40 or s.count(",") >= 3):
        return [p.strip() for p in s.split(",") if p.strip()]
    return [s]


def _finalize_address_lines(lines):
    """Flatten logical address parts so each line prints on its own row on the PDF."""
    out = []
    for line in lines:
        out.extend(_split_address_line_for_display(line))
    return out if out else ["—"]


def _fmt_qty_uom(qty, uom):
    """Compact qty string for packing list lot breakdown."""
    if not isinstance(qty, (int, float)):
        return str(qty)
    s = f"{round(qty, 4):.4f}".rstrip("0").rstrip(".")
    return f"{s} {uom}".strip() if (uom or "").strip() else s


def _lots_maps_for_shipment(shipment):
    """
    Build two lookup maps for lot display strings (lot # + qty/UoM):

    - By Item.pk on the **lot** (warehouse lot's item row)
    - By **SKU** (stripped) — needed when the SO line points at a different Item row than the
      allocated lot (same SKU, e.g. duplicate item records); SO 1023-style cases.

    Sources: LotTransactionLog (sale) + InventoryTransaction for this shipment id in notes.
    Dedupes physical moves by (lot_id, qty).
    """
    from collections import defaultdict

    from .models import InventoryTransaction, LotTransactionLog

    needle = f"Shipment {shipment.id}"
    by_item = defaultdict(list)
    by_sku = defaultdict(list)
    seen = set()

    def _append_from_lot(lot, lot_number_for_display, qty, uom):
        if not lot or not lot.id or not lot.item_id:
            return
        dedupe_key = (lot.id, round(float(qty or 0), 6))
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        qty_part = _fmt_qty_uom(float(qty or 0), uom)
        lot_part = (lot_number_for_display or lot.lot_number or "").strip() or "—"
        fragment = f"{lot_part} ({qty_part})"
        by_item[lot.item_id].append(fragment)
        sku_key = (getattr(lot.item, "sku", None) or "").strip()
        if sku_key:
            by_sku[sku_key].append(fragment)

    logs = (
        LotTransactionLog.objects.filter(
            sales_order_id=shipment.sales_order_id,
            transaction_type__in=("sale", "sales"),
            notes__contains=needle,
        )
        .select_related("lot", "lot__item")
        .order_by("lot_number", "id")
    )
    for log in logs:
        if not log.lot_id or not log.lot:
            continue
        qty = abs(log.quantity_change or 0)
        uom = (log.unit_of_measure or "").strip()
        _append_from_lot(log.lot, log.lot_number, qty, uom)

    inv_txns = (
        InventoryTransaction.objects.filter(notes__contains=needle, quantity__lt=0)
        .select_related("lot", "lot__item")
        .order_by("id")
    )
    for inv in inv_txns:
        lot = inv.lot
        if not lot:
            continue
        qty = abs(inv.quantity or 0)
        uom = (getattr(lot.item, "unit_of_measure", None) or "").strip()
        _append_from_lot(lot, lot.lot_number, qty, uom)

    return (
        {k: "; ".join(v) for k, v in by_item.items()},
        {k: "; ".join(v) for k, v in by_sku.items()},
    )


def _build_shipment_line_items(shipment):
    """Line rows for packing list: shipped qty per SO line + lot breakdown from checkout logs."""
    sales_order = shipment.sales_order
    lots_by_item_id, lots_by_sku = _lots_maps_for_shipment(shipment)
    si_items = list(shipment.items.select_related("sales_order_item__item").all())
    items = []
    for si in si_items[:50]:
        so_item = si.sales_order_item
        it = getattr(so_item, "item", None) if so_item else None
        sku = (it.sku if it else "") or ""
        sku_key = sku.strip()
        name = (it.name if it else "") or ""
        qty = getattr(si, "quantity_shipped", 0) or 0
        uom = (it.unit_of_measure if it else "") or ""
        qty_display = (
            f"{round(qty, 2):.2f}".rstrip("0").rstrip(".")
            if isinstance(qty, (int, float))
            else str(qty)
        )
        qty_with_uom = f"{qty_display} {uom}".strip() if uom else qty_display
        lot_str = lots_by_item_id.get(so_item.item_id, "") or (
            lots_by_sku.get(sku_key, "") if sku_key else ""
        )
        if not lot_str:
            lot_str = "Drop ship" if getattr(sales_order, "drop_ship", False) else "—"
        items.append(
            {
                "sku": sku[:40],
                "description": (name or sku)[:50],
                "quantity": qty_with_uom[:24],
                "lots": lot_str[:500],
            }
        )
    if not items:
        items = [{"sku": "—", "description": "—", "quantity": "—", "lots": "—"}]
    return items


def _piece_dimension_rows_from_shipment(shipment):
    """Build [{piece_num, dimensions, weight}, ...] for the packing list table."""
    rows = []
    if not shipment:
        return rows
    pd = getattr(shipment, "piece_dimensions", None) or []
    pw = getattr(shipment, "piece_weights", None) or []
    if isinstance(pd, list):
        for i, dim in enumerate(pd):
            s = (str(dim) if dim is not None else "").strip()
            if not s:
                continue
            wt = ""
            if isinstance(pw, list) and i < len(pw):
                wt = (str(pw[i]) if pw[i] is not None else "").strip()
            rows.append(
                {
                    "piece_num": i + 1,
                    "dimensions": s,
                    "weight": wt or "—",
                }
            )
    if not rows:
        blob = (getattr(shipment, "dimensions", None) or "").strip()
        if blob:
            rows.append({"piece_num": 1, "dimensions": blob, "weight": "—"})
    return rows


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
    if not ship_to_lines:
        ship_to_lines = [sales_order.customer_name or "—"]
    ship_to_lines = _finalize_address_lines(ship_to_lines)
    ship_to_text = "\n".join(ship_to_lines)

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
    if not bill_to_lines:
        bill_to_lines = [sales_order.customer_name or "—"]
    bill_to_lines = _finalize_address_lines(bill_to_lines)
    bill_to_text = "\n".join(bill_to_lines)

    pack_date = timezone.now().date()
    date_str = pack_date.strftime('%Y-%m-%d')
    order_date_str = sales_order.order_date.strftime('%Y-%m-%d') if sales_order.order_date else ''
    ship_date_dt = sales_order.actual_ship_date or sales_order.expected_ship_date
    ship_date_str = ship_date_dt.strftime('%Y-%m-%d') if ship_date_dt else ''
    po_ref = (sales_order.customer_reference_number or '').strip()
    so_number = (sales_order.so_number or '').strip()
    po_so_str = f"{po_ref} / {so_number}" if po_ref and so_number else (so_number or po_ref or '—')

    latest_shipment = sales_order.shipments.order_by('-created_at').first()
    if latest_shipment and getattr(latest_shipment, "ship_date", None):
        ship_date_str = latest_shipment.ship_date.strftime('%Y-%m-%d')
    dimensions = ''
    pieces = ''
    carrier = (getattr(sales_order, "carrier", None) or "").strip() or "—"
    tracking_number = (getattr(sales_order, "tracking_number", None) or "").strip() or "—"
    piece_dimension_rows = []
    if latest_shipment:
        dimensions = (latest_shipment.dimensions or '').strip()
        if latest_shipment.pieces is not None:
            pieces = str(latest_shipment.pieces)
        tn = (latest_shipment.tracking_number or "").strip()
        if tn:
            tracking_number = tn
        piece_dimension_rows = _piece_dimension_rows_from_shipment(latest_shipment)

    # Line items: prefer this release (latest shipment) with lot numbers from checkout logs
    if latest_shipment:
        items = _build_shipment_line_items(latest_shipment)
    else:
        items = []
        for item in sales_order.items.select_related("item").all()[:50]:
            it = getattr(item, "item", None)
            sku = (it.sku if it else "") or ""
            name = (it.name if it else "") or ""
            qty = getattr(item, "quantity_ordered", 0) or 0
            uom = (it.unit_of_measure if it else "") or ""
            qty_display = (
                f"{round(qty, 2):.2f}".rstrip("0").rstrip(".")
                if isinstance(qty, (int, float))
                else str(qty)
            )
            qty_with_uom = f"{qty_display} {uom}".strip() if uom else qty_display
            items.append(
                {
                    "sku": sku[:40],
                    "description": (name or sku)[:50],
                    "quantity": qty_with_uom[:20],
                    "lots": "—",
                }
            )
        if not items:
            items = [{"sku": "—", "description": "—", "quantity": "—", "lots": "—"}]

    logo_base64 = get_batch_ticket_logo_base64_cached()

    return {
        'so_number': so_number,
        'ship_to_text': ship_to_text,
        'bill_to_text': bill_to_text,
        'ship_to_lines': ship_to_lines,
        'bill_to_lines': bill_to_lines,
        'date_str': date_str,
        'order_date_str': order_date_str or '—',
        'ship_date_str': ship_date_str or '—',
        'po_ref': po_ref or '—',
        'po_so_str': po_so_str,
        'dimensions': dimensions or '—',
        'pieces': pieces or '—',
        'carrier': carrier,
        'tracking_number': tracking_number,
        'piece_dimension_rows': piece_dimension_rows,
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

        so = (getattr(sales_order, "so_number", None) or "") or ""
        out = html_string_to_pdf_bytes(html_string, log_label=f"Packing list {so}".strip() or "Packing list PDF")
        if out:
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
    base['carrier'] = (getattr(sales_order, 'carrier', None) or '').strip() or '—'
    base['tracking_number'] = (shipment.tracking_number or '').strip() or '—'
    base['piece_dimension_rows'] = _piece_dimension_rows_from_shipment(shipment)
    base["line_items"] = _build_shipment_line_items(shipment)
    return base


def generate_packing_list_pdf_from_shipment(shipment):
    """Generate packing list PDF for a single shipment (one per release)."""
    try:
        from jinja2 import Environment, FileSystemLoader
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
        out = html_string_to_pdf_bytes(
            html_string,
            log_label=f"Packing list shipment {getattr(shipment, 'id', '')}",
        )
        if out:
            logger.info("Packing list PDF (shipment %s): size=%s", shipment.id, len(out))
        return out
    except Exception as e:
        logger.warning("Packing list from shipment failed: %s", e, exc_info=True)
        return None
