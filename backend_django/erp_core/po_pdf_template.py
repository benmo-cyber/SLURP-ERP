"""
Fill PO template PDF with purchase order data.
Read the document, find each placeholder, redact only that text using the CELL'S
fill color (so it blends), then put the correct value there. Unused placeholders
are redacted in the same cell fill color. Tax is not used.
Requires: pip install pymupdf
"""
from pathlib import Path
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def _get_cell_fill_color(page, rect_tuple):
    """
    Sample the page at the top-left of the cell (just outside the text rect) to get
    the background fill color for that cell. Return (r, g, b) in 0..1 for PyMuPDF.
    """
    import fitz
    if not rect_tuple or len(rect_tuple) < 4:
        return (1, 1, 1)
    x0, y0, x1, y1 = rect_tuple[:4]
    # Sample a small area just above/left of the text to get cell background (not the text itself)
    sample = fitz.Rect(max(0, x0 - 4), max(0, y0 - 4), x0 + 2, y0 + 2)
    if sample.width < 1 or sample.height < 1:
        return (1, 1, 1)
    try:
        pix = page.get_pixmap(clip=sample, alpha=False, dpi=72)
        if pix and pix.samples and len(pix.samples) >= 3:
            # Top-left pixel
            r = pix.samples[0] / 255.0
            g = pix.samples[1] / 255.0
            b = pix.samples[2] / 255.0
            return (r, g, b)
    except Exception:
        pass
    return (1, 1, 1)


def get_po_template_pdf_path(project_root=None):
    """Return path to PO template PDF, or None."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent
    backend = Path(__file__).resolve().parent.parent
    for base in (project_root, backend):
        for name in ("PO template1.pdf", "PO template.pdf", "PO_template1.pdf"):
            p = base / name
            if p.exists():
                return str(p.resolve())
    return None


def _one_rect_per_row(rects, y_tolerance=10):
    """Given rects sorted by (y, x), return one rect per row (same y within tolerance). Avoids multiple spans in one cell counting as multiple cells."""
    if not rects:
        return []
    out = []
    last_y = None
    for r in rects:
        y = r[1]
        if last_y is None or abs(y - last_y) > y_tolerance:
            out.append(r)
            last_y = y
    return out


def _find_rects(page, search_text):
    """Return list of (x0, y0, x1, y1, fontsize) for each occurrence of search_text. Sorted by (y, x)."""
    import fitz
    try:
        rects = page.search_for(search_text, quads=False)
        if rects:
            out = [(r.x0, r.y0, r.x1, r.y1, 10) for r in rects]
            out.sort(key=lambda c: (c[1], c[0]))
            return out
        want = (search_text or "").strip().lower()
        if len(want) < 2:
            return []
        out = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").lower()
                    if want in text:
                        bbox = span.get("bbox")
                        if bbox and len(bbox) >= 4:
                            out.append((bbox[0], bbox[1], bbox[2], bbox[3], span.get("size", 10)))
        out.sort(key=lambda c: (c[1], c[0]))
        return out
    except Exception as e:
        logger.warning("_find_rects %s: %s", search_text[:30], e)
    return []


def _put_value(page, rect, value, fontname="helv", fontsize=10, right_align=False):
    """
    Redact only the placeholder text in this rect, using the CELL's fill color (so it blends).
    Then insert our value. If value is empty, we only redact (unused placeholder).
    """
    import fitz
    if not rect:
        return
    x0, y0, x1, y1, fs = rect
    r = fitz.Rect(x0, y0, x1, y1)
    fill_color = _get_cell_fill_color(page, rect)
    page.add_redact_annot(r, fill=fill_color)
    page.apply_redactions()
    if value is None or str(value).strip() == "":
        return
    val = str(value).strip()[:60]
    fs_use = min(fs, fontsize)
    try:
        if right_align:
            page.insert_textbox(r, val, fontsize=fs_use, fontname=fontname, color=(0, 0, 0), align=fitz.TEXT_ALIGN_RIGHT)
        else:
            page.insert_text((x0, y0 + fs_use * 0.85), val, fontsize=fs_use, fontname=fontname, color=(0, 0, 0))
    except Exception as e:
        logger.warning("insert %s: %s", val[:20], e)


def _put_value_multi(page, rects, values, fontname="helv", fontsize=10, right_align=False):
    """For each rect, redact then insert corresponding value. values can be single value or list."""
    if not rects:
        return
    vals = values if isinstance(values, list) else [values] * len(rects)
    for i, rect in enumerate(rects):
        if i >= len(vals):
            break
        _put_value(page, rect, vals[i], fontname=fontname, fontsize=fontsize, right_align=right_align)


def fill_po_template_pdf(template_path, purchase_order):
    """
    Open PO template, find each placeholder, redact only that text, insert our value.
    Same principle as batch ticket: read document, put correct information in correct place.
    """
    import fitz
    try:
        doc = fitz.open(template_path)
        if doc.page_count == 0:
            doc.close()
            return None
        page = doc[0]

        # --- Data from PO ---
        order_date = purchase_order.order_date.strftime("%b %d, %Y") if getattr(purchase_order, "order_date", None) else ""
        delivery_date = (purchase_order.expected_delivery_date or getattr(purchase_order, "required_date", None))
        delivery_date = delivery_date.strftime("%b %d, %Y") if delivery_date else ""

        payment_terms = ""
        try:
            from .models import Vendor
            v = Vendor.objects.filter(name=purchase_order.vendor_customer_name).first()
            if v and getattr(v, "payment_terms", None):
                payment_terms = (v.payment_terms or "").strip()
        except Exception:
            pass

        ship_via = (getattr(purchase_order, "shipping_method", None) or getattr(purchase_order, "carrier", None) or "").strip()
        requested_by = getattr(purchase_order, "requested_by", None) or ""
        status_label = (getattr(purchase_order, "status", None) or "draft").capitalize()

        vendor_name = (purchase_order.vendor_customer_name or "").strip()
        vendor_addr1 = (purchase_order.vendor_address or "").strip()
        vendor_addr2 = ", ".join(filter(None, [purchase_order.vendor_city, purchase_order.vendor_state, purchase_order.vendor_zip]))
        bill_to_name = "Wildwood Ingredients, LLC"
        bill_addr1 = "6431 Michels Drive"
        bill_addr2 = "Washington, MO 63090"
        ship_to_name = (purchase_order.ship_to_name or "").strip()
        ship_addr1 = (purchase_order.ship_to_address or "").strip()
        ship_addr2 = ", ".join(filter(None, [purchase_order.ship_to_city, purchase_order.ship_to_state, purchase_order.ship_to_zip]))
        notes_text = (getattr(purchase_order, "notes", None) or "").strip()

        # --- Header: one placeholder → one value (redact exact bbox, then insert) ---
        r = _find_rects(page, "[PO-0001]")
        if r:
            _put_value(page, r[0], purchase_order.po_number or "")

        for search, val in [
            ("Draft / Open / Closed", status_label),
            ("Open / Closed", status_label),
        ]:
            r = _find_rects(page, search)
            if r:
                _put_value(page, r[0], val)
                break

        # PO Date and Delivery Date: template often has two "[Month DD, YYYY]"
        r_date = _find_rects(page, "[Month DD, YYYY]")
        if r_date and len(r_date) >= 1:
            _put_value(page, r_date[0], order_date)
        if r_date and len(r_date) >= 2:
            _put_value(page, r_date[1], delivery_date)

        for search, val in [
            ("[Name]", requested_by),
            ("[Net 30]", payment_terms),
            ("[Carrier / Method]", ship_via),
        ]:
            r = _find_rects(page, search)
            if r:
                _put_value(page, r[0], val)

        # Vendor & shipping blocks
        r = _find_rects(page, "[Supplier Name]")
        if r:
            _put_value(page, r[0], vendor_name)

        # Address lines: usually 3 occurrences (Vendor, Bill To, Ship To)
        r_a1 = _find_rects(page, "[Address Line 1]")
        if r_a1 and len(r_a1) >= 3:
            _put_value_multi(page, r_a1[:3], [vendor_addr1, bill_addr1, ship_addr1])
        r_a2 = _find_rects(page, "[Address Line 2]")
        if r_a2 and len(r_a2) >= 3:
            _put_value_multi(page, r_a2[:3], [vendor_addr2, bill_addr2, ship_addr2])

        for search, val in [
            ("[Your Company Name]", bill_to_name),
            ("[Receiving Contact]", ship_to_name),
        ]:
            r = _find_rects(page, search)
            if r:
                _put_value(page, r[0], val)

        # Optional fields: only replace if we have a value; otherwise redact placeholder so cell is blank
        for search, val in [
            ("[Contact Name]", ""),
            ("[Email / Phone]", ""),
            ("[AP / Purchasing Contact]", ""),
            ("[Site / Warehouse]", ""),
        ]:
            r = _find_rects(page, search)
            if r:
                _put_value(page, r[0], val)

        r = _find_rects(page, "[Special Delivery Instructions]")
        if r:
            _put_value(page, r[0], notes_text)

        # --- Line items: up to 4 rows. Find placeholders in data area only (y > 320 so we skip header) ---
        items = list(purchase_order.items.select_related("item").all())[:4]
        if items:
            # Description: find placeholders; use one rect per ROW (template may split "[Item / Service" and "Description]" in same cell)
            desc_rects = _find_rects(page, "[Item / Service Description]")
            if not desc_rects:
                desc_rects = _find_rects(page, "[Item / Service")
            if not desc_rects:
                desc_rects = _find_rects(page, "[Description]")
            desc_rects = [t for t in desc_rects if t[1] > 320]
            desc_rects = _one_rect_per_row(desc_rects)[:4]
            if len(desc_rects) >= len(items):
                for i, po_item in enumerate(items):
                    item = po_item.item
                    desc = (item.name if item else (po_item.notes or "")) or ""
                    _put_value(page, desc_rects[i], desc[:50], fontsize=9)
                for j in range(len(items), min(4, len(desc_rects))):
                    _put_value(page, desc_rects[j], "")  # blank empty rows

            # Qty: "[ ]" appears in BOTH Qty and Tax columns (8 rects: row1_qty, row1_tax, row2_qty, ...). Use only Qty column (indices 0,2,4,6). Tax is not applicable — never put a value there.
            all_qty_tax = _find_rects(page, "[ ]")
            all_qty_tax = [t for t in all_qty_tax if 320 < t[1] < 450]
            qty_rects = [all_qty_tax[i] for i in (0, 2, 4, 6)] if len(all_qty_tax) >= 8 else all_qty_tax[:4]
            if len(qty_rects) >= len(items):
                for i, po_item in enumerate(items):
                    _put_value(page, qty_rects[i], f"{po_item.quantity_ordered:,.2f}", fontsize=9)
                for j in range(len(items), min(4, len(qty_rects))):
                    _put_value(page, qty_rects[j], "")

            # Unit
            unit_rects = _find_rects(page, "[EA]")
            unit_rects = [t for t in unit_rects if 320 < t[1] < 450][:4]
            if len(unit_rects) >= len(items):
                for i, po_item in enumerate(items):
                    uom = (getattr(po_item.item, "unit_of_measure", None) if po_item.item else None) or "lbs"
                    uom = "ea" if str(uom).lower() in ("ea", "each") else uom
                    _put_value(page, unit_rects[i], uom, fontsize=9)
                for j in range(len(items), min(4, len(unit_rects))):
                    _put_value(page, unit_rects[j], "")

            # Unit price and line total: find "[$0.00]" in data rows only
            dollar_rects = _find_rects(page, "[$0.00]")
            dollar_rects = [t for t in dollar_rects if 320 < t[1] < 450][:8]
            if len(dollar_rects) >= 8:
                unit_price_rects = [dollar_rects[0], dollar_rects[2], dollar_rects[4], dollar_rects[6]]
                line_total_rects = [dollar_rects[1], dollar_rects[3], dollar_rects[5], dollar_rects[7]]
                for i, po_item in enumerate(items):
                    _put_value(page, unit_price_rects[i], f"${(po_item.unit_price or 0):,.2f}", fontsize=9)
                    _put_value(page, line_total_rects[i], f"${po_item.quantity_ordered * (po_item.unit_price or 0):,.2f}", fontsize=9)
                for j in range(len(items), 4):
                    _put_value(page, unit_price_rects[j], "")
                    _put_value(page, line_total_rects[j], "")

            # Tax column: not applicable. Redact placeholder "[]" in Tax cells only (indices 1,3,5,7 if we have 8 rects) with cell fill, insert nothing.
            bracket_rects = _find_rects(page, "[]")
            bracket_rects = [t for t in bracket_rects if 320 < t[1] < 450]
            if len(bracket_rects) >= 8:
                tax_rects = [bracket_rects[i] for i in (1, 3, 5, 7)]
                for rect in tax_rects:
                    _put_value(page, rect, "")

        # --- Notes ---
        r = _find_rects(page, "[Special notes,")
        if not r:
            r = _find_rects(page, "instructions.]")
        if r:
            _put_value(page, r[0], notes_text[:200], fontsize=9)

        # --- Summary: Subtotal, Shipping, Tax, Discount, Total — find value cells (y in summary area) ---
        subtotal = sum((pi.quantity_ordered * (pi.unit_price or 0)) for pi in purchase_order.items.all())
        subtotal = round(subtotal, 2)
        discount = float(getattr(purchase_order, "discount", 0) or 0)
        shipping_cost = float(getattr(purchase_order, "shipping_cost", 0) or 0)
        total = round(subtotal - discount + shipping_cost, 2)
        summary_vals = [
            f"${subtotal:,.2f}",
            f"${shipping_cost:,.2f}",
            "$0.00",
            f"-${discount:,.2f}",
            f"${total:,.2f}",
        ]

        for search in ("[$0.00]", "$0.00"):
            all_rects = _find_rects(page, search)
            summary_rects = [t for t in all_rects if t[1] > 450][-5:]
            if len(summary_rects) >= 5:
                for i, rect in enumerate(summary_rects):
                    _put_value(page, rect, summary_vals[i], fontsize=10, right_align=True)
                break

        buf = BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        doc.close()
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.warning("PO template fill failed: %s", e, exc_info=True)
        return None
