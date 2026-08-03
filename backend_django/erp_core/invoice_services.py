"""
Shared invoice helpers for Issue (draft → sent) used by DRF and slurp_ui.

Draft creation stays in sell_services._create_shipment_invoice (checkout).
PDF generation stays in invoice_pdf_html.generate_invoice_pdf_from_html.
"""
from __future__ import annotations

import logging

from .models import Invoice

logger = logging.getLogger(__name__)


class InvoiceFlowError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def issue_invoice(
    invoice: Invoice,
    *,
    carrier: str | None = None,
    tracking_number: str | None = None,
    send_email: bool = True,
) -> Invoice:
    """
    Move a draft invoice to Issued (``status='sent'``).

    Requires sales-order carrier + tracking when linked to an SO. Optional
    ``carrier`` / ``tracking_number`` update the SO first when provided.
    """
    if invoice.status == "sent":
        raise InvoiceFlowError(f"Invoice {invoice.invoice_number} is already issued.")
    if invoice.status == "cancelled":
        raise InvoiceFlowError(f"Invoice {invoice.invoice_number} is cancelled.")
    if invoice.status != "draft":
        raise InvoiceFlowError(
            f"Only draft invoices can be issued. Current status: {invoice.status}"
        )

    so = None
    if invoice.sales_order_id:
        so = invoice.sales_order
        if so is None:
            from .models import SalesOrder

            so = SalesOrder.objects.filter(pk=invoice.sales_order_id).first()

    if so is not None:
        updates = []
        if carrier is not None and str(carrier).strip():
            so.carrier = str(carrier).strip()
            updates.append("carrier")
        if tracking_number is not None and str(tracking_number).strip():
            so.tracking_number = str(tracking_number).strip()
            updates.append("tracking_number")
        if updates:
            so.save(update_fields=updates)

        c = (getattr(so, "carrier", None) or "").strip()
        t = (getattr(so, "tracking_number", None) or "").strip()
        if not c or not t:
            raise InvoiceFlowError(
                "Carrier and tracking number must be entered on the sales order "
                "before the invoice can be moved to Issued/Sent."
            )

    invoice.status = "sent"
    invoice.save(update_fields=["status"])

    if send_email:
        try:
            from .email_service import send_invoice_email
            from .invoice_pdf_html import generate_invoice_pdf_from_html

            pdf_content = generate_invoice_pdf_from_html(invoice)
            send_invoice_email(invoice, pdf_content)
        except Exception as e:
            logger.error("Failed to send invoice email for %s: %s", invoice.invoice_number, e)

    return invoice


def cancel_invoice(invoice: Invoice) -> Invoice:
    """Void an invoice (``status='cancelled'``). Paid invoices cannot be voided here."""
    if invoice.status == "cancelled":
        raise InvoiceFlowError(f"Invoice {invoice.invoice_number} is already cancelled.")
    if invoice.status == "paid":
        raise InvoiceFlowError(
            f"Invoice {invoice.invoice_number} is paid; cannot void from this screen."
        )
    invoice.status = "cancelled"
    invoice.save(update_fields=["status"])
    return invoice
