"""
Parse customer PO documents (PDF or plain text) and return structured data
for auto-filling the Create Sales Order form.
"""
import re
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF file. Tries default then layout mode. Returns empty string if not a PDF or on error."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(file_bytes))
        parts = []
        for page in reader.pages:
            text = None
            try:
                text = page.extract_text()
            except Exception as e:
                logger.warning("Failed to extract text from PDF page: %s", e)
            if not text or not text.strip():
                try:
                    text = page.extract_text(extraction_mode="layout")
                except Exception:
                    pass
            if text and text.strip():
                parts.append(text)
        return "\n".join(parts) if parts else ""
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return ""


def _po_number_from_filename(filename: str) -> Optional[str]:
    """Try to get PO number from filename like 'Purchase Order 00011638.pdf'."""
    if not filename:
        return None
    base = filename.replace(".pdf", "").replace(".PDF", "").strip()
    m = re.search(r"(\d{5,})", base)
    if m:
        return m.group(1)
    m = re.search(r"([A-Z0-9\-]{4,20})", base, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def parse_customer_po(file_bytes: bytes, filename: str = "") -> dict:
    """
    Parse a customer PO document and return structured data for the sales order form.
    Supports PDF (text extraction). Returns a dict with:
      - customer_po_number, customer_name, address fields, requested_ship_date, items
      - extracted_preview: first 400 chars of extracted text (for debugging)
      - warning: message if no text or partial extraction
    """
    text = ""
    is_pdf = filename.lower().endswith(".pdf") or (file_bytes[:4] == b"%PDF")
    if is_pdf:
        text = extract_text_from_pdf(file_bytes)
    else:
        try:
            text = file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return _empty_result("Unsupported file type. Please use PDF or plain text.")

    preview = (text.strip()[:400] + "…") if len(text.strip()) > 400 else text.strip()
    if not text or not text.strip():
        return _empty_result(
            "No text could be extracted from the document. If it's a scanned PDF, try a document with selectable text."
        )

    result = _parse_po_text(text)
    result["extracted_preview"] = preview
    if not result.get("customer_po_number") and filename:
        from_filename = _po_number_from_filename(filename)
        if from_filename:
            result["customer_po_number"] = from_filename
    return result


def _empty_result(message: str = "") -> dict:
    return {
        "customer_po_number": "",
        "customer_name": "",
        "customer_address": "",
        "customer_city": "",
        "customer_state": "",
        "customer_zip": "",
        "customer_country": "",
        "customer_phone": "",
        "requested_ship_date": None,
        "items": [],
        "warning": message,
        "extracted_preview": "",
    }


def _parse_po_text(text: str) -> dict:
    """Apply heuristics to extract PO fields from raw text."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    result = _empty_result()

    # --- PO number (avoid capturing labels like "DATE", "NUMBER") ---
    _po_blacklist = frozenset({"date", "number", "no", "reference", "ref", "id", "na", "n/a", "tbd", "required", "ship", "order"})
    def _valid_po_number(val: str) -> bool:
        if not val or len(val) < 2 or len(val) > 50:
            return False
        v = val.strip().lower()
        if v in _po_blacklist:
            return False
        if re.match(r"^[a-z]+$", v) and len(v) <= 6:
            return False
        return True

    po_patterns = [
        r"Purchase\s*Order\s*(?:#|Number)?\s*:?\s*(\d[\d\-]*)",
        r"P\.?O\.?\s*(?:#|Number)?\s*:?\s*(\d[\d\-]*)",
        r"Order\s*#\s*:?\s*(\d[\d\-]*)",
        r"(?:PO\s*#?|P\.?O\.?\s*#?)\s*:?\s*([A-Za-z0-9\-]+)",
        r"(?:Order\s*#?|Order\s*Number)\s*:?\s*([A-Za-z0-9\-]+)",
        r"(?:Ref(?:erence)?\s*#?|Reference\s*Number)\s*:?\s*([A-Za-z0-9\-]+)",
        r"\bPO\s*:?\s*([A-Z0-9\-]{4,20})\b",
    ]
    for pat in po_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if _valid_po_number(val):
                result["customer_po_number"] = val
                break

    # --- Dates (ship date, required date, etc.) ---
    date_patterns = [
        r"(?:Requested\s*Ship|Ship\s*Date|Required\s*Date|Delivery\s*Date|Expected\s*Ship)\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
        r"(?:Ship|Delivery)\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
        r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\s*(?:\(.*ship|ship.*\))?",
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            g = m.groups()
            try:
                month, day, year = int(g[0]), int(g[1]), int(g[2])
                if year < 100:
                    year += 2000
                result["requested_ship_date"] = f"{year:04d}-{month:02d}-{day:02d}"
                break
            except (ValueError, IndexError):
                continue

    # --- Ship-to / customer name and address (common block) ---
    ship_section = _find_ship_to_section(text)
    if ship_section:
        result["customer_name"] = ship_section.get("name") or result["customer_name"]
        result["customer_address"] = ship_section.get("address") or result["customer_address"]
        result["customer_city"] = ship_section.get("city") or result["customer_city"]
        result["customer_state"] = ship_section.get("state") or result["customer_state"]
        result["customer_zip"] = ship_section.get("zip") or result["customer_zip"]
        result["customer_country"] = ship_section.get("country") or result["customer_country"]
        result["customer_phone"] = ship_section.get("phone") or result["customer_phone"]

    # If we still don't have customer name, try "Bill To" or first non-empty line after a header
    if not result["customer_name"]:
        for pat in [r"(?:Bill\s*To|Sold\s*To|Customer)\s*:?\s*(.+?)(?:\n|$)", r"^([A-Za-z0-9\s&.,\-]+(?:Inc|LLC|Corp|Co\.?|Ltd)\.?)\s*$"]:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                name = m.group(1).strip()
                if len(name) > 2 and len(name) < 200:
                    result["customer_name"] = name
                    break

    # --- Line items ---
    result["items"] = _parse_line_items(text)

    # Ensure we don't leave warning when we have no message
    if not result.get("warning"):
        result.pop("warning", None)
    if "extracted_preview" not in result:
        result["extracted_preview"] = (text.strip()[:400] + "…") if len(text.strip()) > 400 else text.strip()
    return result


def _find_ship_to_section(text: str) -> Optional[dict]:
    """Try to find Ship To / Deliver To block and parse name, address, city, state, zip, country, phone."""
    out = {}
    for header in [r"Ship\s*To\s*:?", r"Deliver(?:y)?\s*To\s*:?", r"Ship\s*To\s*Address\s*:?", r"Delivery\s*Address\s*:?"]:
        m = re.search(header + r"\s*(.+?)(?=(?:Bill\s*To|Sold\s*To|PO\s*#|Order\s*#|Item|Qty|Description|^\s*$|\n\n))", text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if not m:
            m = re.search(header + r"\s*(.+?)(?=\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)
        if m:
            block = m.group(1).strip()
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            out["name"] = lines[0]
            addr_lines = []
            for line in lines[1:]:
                # US: City, ST 12345 or City, ST 12345-6789
                city_state = re.match(r"^(.+?),\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)\s*(.*)$", line)
                if city_state:
                    out["city"] = city_state.group(1).strip()
                    out["state"] = city_state.group(2).strip()
                    out["zip"] = city_state.group(3).strip()
                    rest = city_state.group(4).strip()
                    if rest and rest.lower() not in ("usa", "us"):
                        out["country"] = rest
                    elif not out.get("country"):
                        out["country"] = "USA"
                    break
                # International: City PostalCode Country or City, PostalCode Country
                intl = re.match(r"^(.+?)[,\s]+([A-Z0-9\s\-]{3,12})\s+([A-Za-z\s]{2,})$", line)
                if intl and not out.get("zip"):
                    out["city"] = intl.group(1).strip()
                    out["zip"] = intl.group(2).strip()
                    out["country"] = intl.group(3).strip()
                    break
                # Line that looks like street address (starts with digit or contains comma)
                if re.match(r"^\d", line) or ("," in line and len(line) > 10):
                    addr_lines.append(line)
                elif not out.get("city") and len(line) > 2 and not re.match(r"^(?:Phone|Tel|Fax|Ph)\s*:?", line, re.I):
                    addr_lines.append(line)
            if addr_lines:
                out["address"] = "\n".join(addr_lines) if len(addr_lines) > 1 else addr_lines[0]
            phone_m = re.search(r"(?:Phone|Tel|Ph)\s*:?\s*([\d\s\-\.\(\)]+)", block, re.IGNORECASE)
            if phone_m:
                out["phone"] = phone_m.group(1).strip()
            if out.get("name"):
                return out
    return out


def _parse_line_items(text: str) -> list:
    """Extract line items: description, quantity, unit, unit_price. Uses table-like and inline patterns."""
    items = []
    lines = text.splitlines()

    # Find table header row
    table_start = -1
    for i, line in enumerate(lines):
        if re.search(r"(?:Qty|Quantity)\s+.+(?:Description|Item|Product).+(?:Price|Unit|Amount)", line, re.IGNORECASE):
            table_start = i
            break
        if re.search(r"Description\s+Qty\s+Unit\s+Price", line, re.IGNORECASE):
            table_start = i
            break
        if re.search(r"Item\s+Description\s+Quantity\s+Price", line, re.IGNORECASE):
            table_start = i
            break

    if table_start >= 0:
        for i in range(table_start + 1, min(table_start + 50, len(lines))):
            row = lines[i]
            if not row.strip():
                continue
            # One or two numbers at start (line#, qty), then description, then optional unit, then price (with optional $)
            row_match = re.match(
                r"^\s*(?:\d+\.?\s*)?\s*(\d+(?:\.\d*)?)\s+(.+?)\s+(?:([A-Za-z]+)\s+)?\$?\s*(\d+(?:\.\d{2})?)\s*$",
                row,
            )
            if row_match:
                qty, desc, unit, price = row_match.groups()
                desc = desc.strip()
                if len(desc) >= 2:
                    items.append({
                        "description": desc,
                        "quantity_ordered": float(qty),
                        "unit": (unit or "lbs").strip(),
                        "unit_price": float(price),
                        "vendor_part_number": "",
                        "notes": "",
                    })
                continue
            simple = re.match(r"^\s*(\d+(?:\.\d*)?)\s+(.+?)\s+\$?(\d+(?:\.\d{2})?)\s*$", row)
            if simple:
                qty, desc, price = simple.groups()
                desc = desc.strip()
                if len(desc) >= 2:
                    items.append({
                        "description": desc,
                        "quantity_ordered": float(qty),
                        "unit": "lbs",
                        "unit_price": float(price),
                        "vendor_part_number": "",
                        "notes": "",
                    })

    # Fallback: any line that has number + text + number (qty ... price)
    if not items:
        for line in lines:
            line = line.strip()
            if len(line) < 10:
                continue
            # Match: leading number (qty), middle text (description), trailing $? number (price)
            m = re.match(r"^\s*(\d+(?:\.\d*)?)\s+(.+?)\s+\$?(\d+(?:\.\d{2})?)\s*$", line)
            if m:
                qty, desc, price = m.groups()
                desc = desc.strip()
                if len(desc) >= 2 and float(price) > 0:
                    items.append({
                        "description": desc,
                        "quantity_ordered": float(qty),
                        "unit": "lbs",
                        "unit_price": float(price),
                        "vendor_part_number": "",
                        "notes": "",
                    })
                    if len(items) >= 30:
                        break

    # Inline pattern in full text: "100 Product Name @ 1.50" or "100 x Product Name 1.50"
    if not items:
        fallback = re.findall(
            r"(?:^|\n)\s*(\d+(?:\.\d*)?)\s+(?:x\s*)?(.+?)\s+(?:@\s*)?\$?\s*(\d+(?:\.\d{2})?)\s*(?:\n|$)",
            text,
            re.IGNORECASE,
        )
        for qty, desc, price in fallback[:20]:
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) >= 2:
                items.append({
                    "description": desc,
                    "quantity_ordered": float(qty),
                    "unit": "lbs",
                    "unit_price": float(price),
                    "vendor_part_number": "",
                    "notes": "",
                })

    return items
