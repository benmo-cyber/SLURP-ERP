"""
Invoice PDF from template — same flow as batch ticket.
Use Invoice template.pdf with labels on each fillable area; find each label in the PDF
and insert the corresponding data (ship-to from sales order, bill-to from customer profile,
PO/cust ref from sales order).
Requires: pymupdf (pip install pymupdf).
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def _norm(s):
    return (s or "").replace("\ufb01", "fi").replace("\u01a0", "t").replace("\u01a1", "t").lower()


def _find_text_bbox(page, search_text, exclude_containing=None, topmost=False):
    """Return (x1, y0, fontsize) for placing value after the label. PyMuPDF page."""
    try:
        raw = search_text.strip()
        want_exact = _norm(raw)
        want_no_colon = _norm(raw.rstrip(":").strip())
        key_phrase = (want_no_colon.split(":")[0].strip() if ":" in raw else want_no_colon)
        excludes = [_norm(x) for x in (exclude_containing or [])]
        candidates = []
        for want in [want_exact, want_no_colon, key_phrase]:
            if not want or len(want) < 2:
                continue
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = _norm(span.get("text", ""))
                        if want in text:
                            if excludes and any(ex in text for ex in excludes):
                                continue
                            bbox = span.get("bbox")
                            if bbox and len(bbox) >= 4:
                                candidates.append((bbox[2], bbox[1], span.get("size", 10)))
        if not candidates:
            return None
        if topmost:
            candidates.sort(key=lambda c: c[1])
        return candidates[0]
    except Exception:
        pass
    return None


def _find_text_bbox_origin(page, search_text, topmost=False, exclude_containing=None):
    """Return (x0, y0, fontsize) for the left edge of the label."""
    try:
        raw = search_text.strip()
        want = _norm(raw)
        want_no_colon = _norm(raw.rstrip(":").strip())
        key_phrase = (want_no_colon.split(":")[0].strip() if ":" in raw else want_no_colon)
        if not want or len(want) < 2:
            return None
        excludes = [_norm(x) for x in (exclude_containing or [])]
        candidates = []
        for w in [want, want_no_colon, key_phrase]:
            if not w or len(w) < 2:
                continue
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = _norm(span.get("text", ""))
                        if w in text:
                            if excludes and any(ex in text for ex in excludes):
                                continue
                            bbox = span.get("bbox")
                            if bbox and len(bbox) >= 4:
                                candidates.append((bbox[0], bbox[1], span.get("size", 10)))
        if not candidates:
            return None
        if topmost:
            candidates.sort(key=lambda c: c[1])
        return candidates[0]
    except Exception:
        pass
    return None


def _find_label_rect(page, search_text, topmost=False, y_min=None, y_max=None):
    """Return (x0, y0, x1, y1, fontsize) of the placeholder text's bbox. Tries exact text and with ** stripped."""
    try:
        raw = search_text.strip()
        # Try: exact, without asterisks, key phrase (e.g. "invoice #" from "**Invoice #**")
        variants = [_norm(raw), _norm(raw.replace("**", "").strip()), _norm(raw.rstrip(":").strip())]
        if ":" in raw:
            variants.append(_norm(raw.split(":")[0].strip()))
        candidates = []
        for want in variants:
            if not want or len(want) < 2:
                continue
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = _norm(span.get("text", ""))
                        if want in text or text in want:
                            bbox = span.get("bbox")
                            if bbox and len(bbox) >= 4:
                                if y_min is not None and bbox[1] < y_min:
                                    continue
                                if y_max is not None and bbox[1] > y_max:
                                    continue
                                candidates.append((bbox[0], bbox[1], bbox[2], bbox[3], span.get("size", 10)))
        if not candidates:
            return None
        if topmost:
            candidates.sort(key=lambda c: (c[1], c[0]))
        return candidates[0]
    except Exception:
        pass
    return None


def _get_section_y_bounds(page, section_label):
    """Return (y_min, y_max) for the section (e.g. 'SHIP TO' -> y of that label, y + 90). None if not found."""
    r = _find_label_rect(page, section_label, topmost=True)
    if not r:
        return None, None
    _, y0, _, _, _ = r
    return y0, y0 + 95


def _get_cells_below_section(page, section_label, max_cells=6, y_extent=95):
    """Find section (e.g. 'SHIP TO'), then return list of (x0, y0, x1, y1, fs) for spans below it, sorted by y then x, up to max_cells."""
    r = _find_label_rect(page, section_label, topmost=True)
    if not r:
        return []
    _, section_y, _, _, _ = r
    y_min = section_y + 5
    y_max = section_y + y_extent
    cells = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                if bbox[1] < y_min or bbox[1] > y_max:
                    continue
                cells.append((bbox[0], bbox[1], bbox[2], bbox[3], span.get("size", 10)))
    cells.sort(key=lambda c: (c[1], c[0]))
    return cells[:max_cells]


def _insert_in_cell_with_label(page, label, value, fontname="helv", fontsize=10, max_len=80, topmost=False, y_min=None, y_max=None):
    """Fill the same cell that contains the label: redact the label text, then insert our value at that position. Returns True if filled."""
    if value is None or str(value).strip() == "":
        return False
    rect_info = _find_label_rect(page, label, topmost=topmost, y_min=y_min, y_max=y_max)
    if not rect_info:
        return False
    x0, y0, x1, y1, fs = rect_info
    try:
        import fitz
        r = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()
    except Exception:
        pass
    page.insert_text(
        (x0, y0 + fs * 0.8),
        str(value).strip()[:max_len],
        fontsize=min(fs, fontsize),
        fontname=fontname,
        color=(0, 0, 0),
    )
    return True


def _fill_rect_with_text(page, x0, y0, x1, y1, fs, value, fontname="helv", max_len=80):
    """Redact the rect and insert value at (x0, y0). Used for section-ordered fill."""
    if value is None or str(value).strip() == "":
        return
    try:
        import fitz
        r = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()
    except Exception:
        pass
    page.insert_text(
        (x0, y0 + (fs or 10) * 0.8),
        str(value).strip()[:max_len],
        fontsize=min(fs or 10, 10),
        fontname=fontname,
        color=(0, 0, 0),
    )


def _insert_in_cell_below(page, header_label, value, fontname="helv", fontsize=10, row_height_pt=18, max_len=80, topmost=False):
    """Put value in the cell *below* the header (e.g. CUST REF # header -> value in row below). Do not replace the header."""
    if value is None or str(value).strip() == "":
        return
    pos = _find_text_bbox_origin(page, header_label, topmost=topmost)
    if not pos:
        return
    x0, y0, fs = pos
    y_below = y0 + row_height_pt
    page.insert_text(
        (x0, y_below + fs * 0.8),
        str(value).strip()[:max_len],
        fontsize=min(fs, fontsize),
        fontname=fontname,
        color=(0, 0, 0),
    )


def get_invoice_template_pdf_path(project_root=None):
    """Return Path to Invoice template.pdf. Prefers project root (WWI ERP), then backend_django, then erp_core."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent
    backend = project_root / "backend_django"
    erp_core = backend / "erp_core"
    candidates = [
        project_root / "Invoice template.pdf",
        project_root / "Invoice Template.pdf",
        backend / "Invoice template.pdf",
        erp_core / "Invoice template.pdf",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _build_ship_to_from_sales_order(so):
    """Ship-to: from completed sales order — ship_to_location or SO legacy address."""
    if not so:
        return {}
    out = {}
    if getattr(so, "ship_to_location", None) and so.ship_to_location:
        loc = so.ship_to_location
        out["company_name"] = (getattr(loc, "location_name", None) or "").strip() or (getattr(loc, "contact_name", None) or "").strip()
        out["street_address"] = (getattr(loc, "address", None) or "").strip()
        out["city"] = (getattr(loc, "city", None) or "").strip()
        out["state"] = (getattr(loc, "state", None) or "").strip()
        out["zipcode"] = (getattr(loc, "zip_code", None) or "").strip()
        out["phone"] = (getattr(loc, "phone", None) or "").strip()
    else:
        out["company_name"] = (getattr(so, "customer_name", None) or "").strip()
        out["street_address"] = (getattr(so, "customer_address", None) or "").strip()
        out["city"] = (getattr(so, "customer_city", None) or "").strip()
        out["state"] = (getattr(so, "customer_state", None) or "").strip()
        out["zipcode"] = (getattr(so, "customer_zip", None) or "").strip()
        out["phone"] = (getattr(so, "customer_phone", None) or "").strip()
    return out


def _build_bill_to_from_customer(customer):
    """Bill-to: from customer profile (customer selected in customer name dropdown on the sales order)."""
    if not customer:
        return {}
    return {
        "company_name": (getattr(customer, "name", None) or "").strip(),
        "street_address": (getattr(customer, "address", None) or "").strip(),
        "city": (getattr(customer, "city", None) or "").strip(),
        "state": (getattr(customer, "state", None) or "").strip(),
        "zipcode": (getattr(customer, "zip_code", None) or "").strip(),
        "phone": (getattr(customer, "phone", None) or "").strip(),
    }


def _normalize_field_name(name):
    """Normalize for matching: lower, strip, collapse spaces/underscores/dashes."""
    if not name:
        return ""
    s = (name or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(s.split())


def _build_form_value_map(ship_to, bill_to, po_number, cust_ref):
    """Map possible form field names (normalized) to values. Used to fill AcroForm widgets."""
    # Keys are normalized; value is the string to put in the field.
    m = {}
    # Ship-to
    for key in ["ship to company name", "shipto company name", "ship to company", "ship to name"]:
        m[key] = ship_to.get("company_name") or ""
    for key in ["ship to street address", "shipto street", "ship to address", "ship to street"]:
        m[key] = ship_to.get("street_address") or ""
    for key in ["ship to city", "shipto city"]:
        m[key] = ship_to.get("city") or ""
    for key in ["ship to state", "shipto state"]:
        m[key] = ship_to.get("state") or ""
    for key in ["ship to zipcode", "ship to zip", "shipto zip", "ship to zip code"]:
        m[key] = ship_to.get("zipcode") or ""
    for key in ["ship to phone", "shipto phone"]:
        m[key] = ship_to.get("phone") or ""
    # Bill-to
    for key in ["bill to company name", "billto company name", "bill to company", "bill to name"]:
        m[key] = bill_to.get("company_name") or ""
    for key in ["bill to street address", "billto street", "bill to address", "bill to street"]:
        m[key] = bill_to.get("street_address") or ""
    for key in ["bill to city", "billto city"]:
        m[key] = bill_to.get("city") or ""
    for key in ["bill to state", "billto state"]:
        m[key] = bill_to.get("state") or ""
    for key in ["bill to zipcode", "bill to zip", "billto zip", "bill to zip code"]:
        m[key] = bill_to.get("zipcode") or ""
    for key in ["bill to phone", "billto phone"]:
        m[key] = bill_to.get("phone") or ""
    # PO / Cust ref
    for key in ["po number", "p.o. number", "po #", "customer po", "customer reference number", "cust ref #", "cust ref", "customer ref", "reference #"]:
        m[key] = po_number or cust_ref or ""
    return m


def _fill_form_fields(doc, value_map):
    """Fill AcroForm widgets by matching field_name to value_map. Call widget.update() after each. Returns count filled."""
    filled = 0
    try:
        # Build ordered list of values for fallback when field names are generic (Text1, Text2, ...)
        order_values = [
            value_map.get("ship to company name"),
            value_map.get("ship to street address"),
            value_map.get("ship to city"),
            value_map.get("ship to state"),
            value_map.get("ship to zipcode"),
            value_map.get("ship to phone"),
            value_map.get("bill to company name"),
            value_map.get("bill to street address"),
            value_map.get("bill to city"),
            value_map.get("bill to state"),
            value_map.get("bill to zipcode"),
            value_map.get("bill to phone"),
            value_map.get("po number") or value_map.get("customer reference number"),
        ]
        order_values = [v for v in order_values if v and str(v).strip()]
        order_index = [0]

        for page in doc:
            for widget in page.widgets():
                name = getattr(widget, "field_name", None) or ""
                norm = _normalize_field_name(name)
                val = None
                if norm:
                    val = value_map.get(norm)
                    if val is None:
                        for key, v in value_map.items():
                            if v and (key in norm or norm in key):
                                val = v
                                break
                # Fallback: fill by order (for generic names like Text1, Text2)
                if (val is None or not str(val).strip()) and order_index[0] < len(order_values):
                    val = order_values[order_index[0]]
                    order_index[0] += 1
                if val is not None and str(val).strip():
                    try:
                        widget.field_value = str(val).strip()[:500]
                        widget.update()
                        filled += 1
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("Invoice form field fill: %s", e)
    return filled


def fill_invoice_template_pdf(template_path, invoice):
    """
    Open Invoice template.pdf. If it has fillable form fields (AcroForm), fill those first.
    Then also try label-based text insertion for any static labels. Flatten so values show.
    """
    try:
        import fitz
    except ImportError:
        return None

    template_path = Path(template_path)
    if not template_path.exists() or template_path.suffix.lower() != ".pdf":
        logger.warning("Invoice template not found or not PDF: %s", template_path)
        return None

    so = getattr(invoice, "sales_order", None)
    customer = getattr(so, "customer", None) if so else None

    ship_to = _build_ship_to_from_sales_order(so)
    bill_to = _build_bill_to_from_customer(customer)
    po_number = (getattr(so, "customer_reference_number", None) or "").strip() if so else ""
    cust_ref = po_number
    so_number = (getattr(so, "so_number", None) or "").strip() if so else ""
    shipped_via = ""
    if so:
        carrier = (getattr(so, "carrier", None) or "").strip()
        tracking = (getattr(so, "tracking_number", None) or "").strip()
        shipped_via = " ".join(filter(None, [carrier, tracking])).strip()
    payment_terms = (getattr(customer, "payment_terms", None) or "").strip() if customer else ""
    so_notes = (getattr(so, "notes", None) or "").strip() if so else ""

    # Combined City, State zipcode (one field in template)
    bill_city_state_zip = ", ".join(filter(None, [
        (bill_to.get("city") or "").strip(),
        (bill_to.get("state") or "").strip(),
        (bill_to.get("zipcode") or "").strip(),
    ])).strip()
    ship_city_state_zip = ", ".join(filter(None, [
        (ship_to.get("city") or "").strip(),
        (ship_to.get("state") or "").strip(),
        (ship_to.get("zipcode") or "").strip(),
    ])).strip()

    invoice_number = (getattr(invoice, "invoice_number", None) or "").strip()
    invoice_date = getattr(invoice, "invoice_date", None)
    if invoice_date and hasattr(invoice_date, "strftime"):
        date_str = invoice_date.strftime("%m/%d/%Y")
    else:
        date_str = str(invoice_date)[:10] if invoice_date else ""

    subtotal_val = getattr(invoice, "subtotal", None)
    tax_val = getattr(invoice, "tax", None)
    freight_val = getattr(invoice, "freight", None)
    grand_total = getattr(invoice, "grand_total", None)
    if grand_total is None and subtotal_val is not None:
        grand_total = (subtotal_val or 0) + (tax_val or 0) + (freight_val or 0)

    def fmt_dollar(v):
        if v is None:
            return ""
        return f"${float(v):,.2f}"

    try:
        doc = fitz.open(str(template_path))
        if len(doc) < 1:
            doc.close()
            return None
        page = doc[0]
        fontname = "helv"

        value_map = _build_form_value_map(ship_to, bill_to, po_number, cust_ref)
        filled = _fill_form_fields(doc, value_map)
        try:
            for p in doc:
                p.flatten()
        except Exception:
            pass
        page = doc[0]

        # Map: placeholder text in the yellow box (exact from template) -> value. Replace placeholder with value.
        placeholders = [
            # Header
            ("Invoice #", invoice_number),
            ("**Invoice #**", invoice_number),
            ("Date", date_str),
            ("**Date**", date_str),
            # BILL TO (4 fields)
            ("Bill-to company name", bill_to.get("company_name")),
            ("**Bill-to company name**", bill_to.get("company_name")),
            ("Bill-to company street address", bill_to.get("street_address")),
            ("**Bill-to company street address**", bill_to.get("street_address")),
            ("Bill to company City, State, zipcode", bill_city_state_zip),
            ("**Bill to company City, State, zipcode**", bill_city_state_zip),
            ("Bill-to company phone number", bill_to.get("phone")),
            ("**Bill-to company phone number**", bill_to.get("phone")),
            # SHIP TO (4 fields)
            ("Ship-to company name", ship_to.get("company_name")),
            ("**Ship-to company name**", ship_to.get("company_name")),
            ("Ship-to company street address", ship_to.get("street_address")),
            ("**Ship-to company street address**", ship_to.get("street_address")),
            ("Ship-to company City, State, zipcode", ship_city_state_zip),
            ("**Ship-to company City, State, zipcode**", ship_city_state_zip),
            ("Ship-to company phone number", ship_to.get("phone")),
            ("**Ship-to company phone number**", ship_to.get("phone")),
            # Comments
            ("Comments or special instructions", so_notes),
            ("**Comments or special instructions**", so_notes),
            # Reference row (placeholders in cells below headers)
            ("customer reference number", cust_ref),
            ("bmer reference nui", cust_ref),
            ("PO number", po_number),
            ("**PO number**", po_number),
            ("SO number", so_number),
            ("**SO number**", so_number),
            ("carrier / tracking number", shipped_via),
            ("er / tracking nuerms from custo", shipped_via),
            # Totals (use placeholder text that's inside the box, not the column header)
            ("**Subtotal**", fmt_dollar(subtotal_val)),
            ("**Shipping**", fmt_dollar(freight_val)),
            ("**Total due**", fmt_dollar(grand_total)),
        ]
        for placeholder_text, value in placeholders:
            if value is None or str(value).strip() == "":
                continue
            _insert_in_cell_with_label(page, placeholder_text, str(value).strip()[:200], topmost=True)

        # Sales tax (box may be labeled SALES TAX or empty)
        if tax_val is not None and fmt_dollar(tax_val):
            _insert_in_cell_with_label(page, "SALES TAX", fmt_dollar(tax_val), topmost=True)

        # Payment terms
        if payment_terms:
            for pt_label in ["payment terms", "**Payment terms**", "PAYMENT TERMS"]:
                if _insert_in_cell_with_label(page, pt_label, payment_terms, topmost=True):
                    break

        # Line items: first row from first invoice item
        items = getattr(invoice, "_prefetched_objects_cache", {}).get("items", None)
        if items is None and hasattr(invoice, "items"):
            try:
                items = list(invoice.items.all())
            except Exception:
                items = []
        if items:
            it = items[0]
            qty = getattr(it, "quantity", None)
            qty_str = f"{qty:.2f}" if qty is not None else ""
            desc = (getattr(it, "description", None) or "").strip()
            if not desc and getattr(it, "item", None):
                desc = (getattr(it.item, "name", None) or getattr(it.item, "sku", None) or "").strip()
            lot = (getattr(it, "lot_number", None) or "").strip()
            up = getattr(it, "unit_price", None)
            up_str = fmt_dollar(up) if up is not None else ""
            line_total = getattr(it, "total", None)
            if line_total is None and qty is not None and up is not None:
                line_total = qty * up
            total_str = fmt_dollar(line_total) if line_total is not None else ""
            for ph, val in [
                ("Quantity", qty_str),
                ("**Quantity**", qty_str),
                ("Item 1 description", desc),
                ("**Item 1 description**", desc),
                ("Item 1 lot number", lot),
                ("**Item 1 lot number**", lot),
                ("Unit price", up_str),
                ("**Unit price**", up_str),
                ("Total", total_str),
                ("**Total**", total_str),
            ]:
                if val:
                    _insert_in_cell_with_label(page, ph, str(val)[:80], topmost=True)

        out = doc.tobytes()
        doc.close()
        logger.info("Invoice PDF: filled template %s for invoice %s (form fields: %s)", template_path.name, getattr(invoice, "invoice_number", "?"), filled)
        return out
    except Exception as e:
        logger.warning("Invoice template fill failed: %s", e)
        return None
