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


def resolve_customer_for_invoice(invoice):
    """
    Which Customer record drives bill-to and payment terms for this invoice.

    Order: (1) sales_order.customer FK, (2) sales_order.contact.customer when SO has no
    customer FK, (3) Customer matched by sales_order.customer_legacy_id → Customer.customer_id,
    (4) invoice.contact.customer.

    PDFs previously only used (1) and (4), so orders with a billing contact + legacy id but
    no SO.customer_id showed bill-to from legacy lines while terms stayed blank.
    """
    if invoice is None:
        return None
    from .models import Customer, CustomerContact, SalesOrder

    so = getattr(invoice, "sales_order", None)
    if so is None and getattr(invoice, "sales_order_id", None):
        try:
            so = (
                SalesOrder.objects.filter(pk=invoice.sales_order_id)
                .select_related("customer", "contact__customer")
                .first()
            )
        except Exception:
            so = None

    if so is not None:
        if getattr(so, "customer_id", None):
            c = getattr(so, "customer", None)
            if c is None:
                try:
                    c = Customer.objects.filter(pk=so.customer_id).first()
                except Exception:
                    c = None
            if c is not None:
                return c

        if getattr(so, "contact_id", None):
            contact = getattr(so, "contact", None)
            if contact is None:
                try:
                    contact = (
                        CustomerContact.objects.select_related("customer")
                        .filter(pk=so.contact_id)
                        .first()
                    )
                except Exception:
                    contact = None
            if contact is not None and getattr(contact, "customer", None) is not None:
                return contact.customer

        legacy = (getattr(so, "customer_legacy_id", None) or "").strip()
        if legacy:
            try:
                c = Customer.objects.filter(customer_id=legacy).first()
                if c is None:
                    c = Customer.objects.filter(customer_id__iexact=legacy).first()
                if c is not None:
                    return c
            except Exception:
                pass

    if getattr(invoice, "contact_id", None):
        contact = getattr(invoice, "contact", None)
        if contact is None:
            try:
                contact = (
                    CustomerContact.objects.select_related("customer")
                    .filter(pk=invoice.contact_id)
                    .first()
                )
            except Exception:
                contact = None
        if contact is not None and getattr(contact, "customer", None) is not None:
            return contact.customer

    # Legacy SO rows often have no customer FK but customer_name matches CRM Customer.name
    if so is not None:
        nm = (getattr(so, "customer_name", None) or "").strip()
        if nm:
            try:
                c = Customer.objects.filter(name__iexact=nm).first()
                if c is not None:
                    return c
            except Exception:
                pass
    inv_nm = (getattr(invoice, "customer_vendor_name", None) or "").strip()
    if inv_nm:
        try:
            c = Customer.objects.filter(name__iexact=inv_nm).first()
            if c is not None:
                return c
        except Exception:
            pass

    return None


def resolve_payment_terms_for_invoice(invoice) -> str:
    """
    CRM stores payment terms on Customer.payment_terms (same record as bill-to_*).

    Try every link that can point at that customer — do not stop at sales_order.customer
    if that row has empty terms (stale row, partial save, or split data). Always read
    payment_terms from the DB so PDF generation is not affected by stale cached instances.
    """
    if invoice is None:
        return ""
    from .models import Customer, CustomerContact, SalesOrder

    def terms_for_customer_pk(pk) -> str:
        if not pk:
            return ""
        try:
            t = Customer.objects.filter(pk=pk).values_list("payment_terms", flat=True).first()
            return (t or "").strip()
        except Exception:
            return ""

    so = getattr(invoice, "sales_order", None)
    if so is None and getattr(invoice, "sales_order_id", None):
        try:
            so = (
                SalesOrder.objects.filter(pk=invoice.sales_order_id)
                .select_related("customer", "contact__customer")
                .first()
            )
        except Exception:
            so = None

    if so is not None:
        if getattr(so, "customer_id", None):
            t = terms_for_customer_pk(so.customer_id)
            if t:
                return t
        if getattr(so, "contact_id", None):
            cid = None
            contact = getattr(so, "contact", None)
            if contact is not None:
                cid = getattr(contact, "customer_id", None)
            if cid is None:
                try:
                    cid = CustomerContact.objects.filter(pk=so.contact_id).values_list(
                        "customer_id", flat=True
                    ).first()
                except Exception:
                    cid = None
            if cid:
                t = terms_for_customer_pk(cid)
                if t:
                    return t
        legacy = (getattr(so, "customer_legacy_id", None) or "").strip()
        if legacy:
            try:
                lid = Customer.objects.filter(customer_id=legacy).values_list("pk", flat=True).first()
                if lid is None:
                    lid = Customer.objects.filter(customer_id__iexact=legacy).values_list("pk", flat=True).first()
                if lid:
                    t = terms_for_customer_pk(lid)
                    if t:
                        return t
            except Exception:
                pass

    if getattr(invoice, "contact_id", None):
        cid = None
        contact = getattr(invoice, "contact", None)
        if contact is not None:
            cid = getattr(contact, "customer_id", None)
        if cid is None:
            try:
                cid = CustomerContact.objects.filter(pk=invoice.contact_id).values_list(
                    "customer_id", flat=True
                ).first()
            except Exception:
                cid = None
        if cid:
            t = terms_for_customer_pk(cid)
            if t:
                return t

    # Same name-based fallback as resolve_customer_for_invoice (terms may live on CRM Customer
    # while SO has no FK — bill-to can still render from legacy SO lines or HQ fields).
    if so is not None:
        nm = (getattr(so, "customer_name", None) or "").strip()
        if nm:
            try:
                lid = Customer.objects.filter(name__iexact=nm).values_list("pk", flat=True).first()
                if lid:
                    t = terms_for_customer_pk(lid)
                    if t:
                        return t
            except Exception:
                pass
    inv_nm = (getattr(invoice, "customer_vendor_name", None) or "").strip()
    if inv_nm:
        try:
            lid = Customer.objects.filter(name__iexact=inv_nm).values_list("pk", flat=True).first()
            if lid:
                t = terms_for_customer_pk(lid)
                if t:
                    return t
        except Exception:
            pass

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
