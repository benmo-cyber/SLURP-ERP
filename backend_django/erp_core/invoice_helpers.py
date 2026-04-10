"""
Invoice business rules shared by models, PDFs, and migrations.
"""
import re
from datetime import date, timedelta
from typing import Any, Optional


def due_date_from_issue_and_payment_terms(
    issue_date: Optional[date],
    payment_terms_str: Optional[str],
) -> Optional[date]:
    """
    Due date = issue (invoice) date + net days from payment terms.

    Parses the first integer in the terms string (e.g. "Net 30" -> 30 days).
    Phrases like "due on receipt" / COD -> same calendar day as issue date.
    If no number is found, defaults to Net 30.
    """
    if issue_date is None:
        return None
    s = (payment_terms_str or "").strip()
    sl = s.lower()
    if "receipt" in sl or sl in ("cod",) or "due on delivery" in sl:
        return issue_date
    m = re.search(r"(\d+)", s)
    if m:
        return issue_date + timedelta(days=int(m.group(1)))
    return issue_date + timedelta(days=30)


def unit_of_measure_for_invoice_line(line: Any) -> str:
    """Resolve selling UoM for an InvoiceItem (item FK, else sales order line item)."""
    item = getattr(line, "item", None)
    if item is not None:
        return (getattr(item, "unit_of_measure", None) or "").strip()
    soi = getattr(line, "sales_order_item", None)
    if soi is not None:
        it = getattr(soi, "item", None)
        if it is not None:
            return (getattr(it, "unit_of_measure", None) or "").strip()
    return ""


def format_invoice_quantity_display(qty: Optional[float], uom: str) -> str:
    """Quantity cell for invoice PDF: number plus UoM when known."""
    if qty is None:
        return "—"
    f = float(qty)
    if abs(f - round(f)) <= 0.001:
        num = str(int(round(f)))
    else:
        num = f"{f:.2f}"
    u = (uom or "").strip()
    return f"{num} {u}" if u else num
