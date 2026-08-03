"""E2E Invoice: draft → issue (sent) + PDF generate."""
import os
import sys
import uuid
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend_django"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")
django.setup()

from erp_core.invoice_services import InvoiceFlowError, issue_invoice
from erp_core.models import Customer, Invoice, SalesOrder
from erp_core.views import generate_invoice_number, generate_sales_order_number


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg):
    print("OK:", msg)


def main():
    tag = uuid.uuid4().hex[:6].upper()
    customer = Customer.objects.create(
        customer_id=f"E2E-INV-{tag}",
        name=f"E2E Invoice Customer {tag}",
        payment_terms="Net 30",
        is_active=True,
    )
    so = SalesOrder.objects.create(
        so_number=generate_sales_order_number(),
        customer=customer,
        customer_name=customer.name,
        status="completed",
        carrier="",
        tracking_number="",
    )
    inv = Invoice.objects.create(
        invoice_number=generate_invoice_number(),
        invoice_type="customer",
        customer_vendor_name=customer.name,
        sales_order=so,
        invoice_date=date.today(),
        due_date=date.today(),
        status="draft",
        subtotal=100.0,
        freight=10.0,
        tax=0.0,
        discount=0.0,
        grand_total=110.0,
        total_amount=110.0,
        notes=f"E2E invoice {tag}",
    )
    ok(f"draft invoice={inv.invoice_number} so={so.so_number}")

    try:
        issue_invoice(inv)
        fail("issue without carrier/tracking should fail")
    except InvoiceFlowError:
        ok("carrier/tracking enforced")

    inv.refresh_from_db()
    if inv.status != "draft":
        fail("should still be draft after failed issue")

    issue_invoice(
        inv,
        carrier="E2E Carrier",
        tracking_number=f"TRK-{tag}",
        send_email=False,
    )
    inv.refresh_from_db()
    so.refresh_from_db()
    if inv.status != "sent":
        fail(f"expected sent, got {inv.status}")
    if so.carrier != "E2E Carrier" or so.tracking_number != f"TRK-{tag}":
        fail("SO carrier/tracking not updated")
    ok("issued (sent); SO tracking updated")

    try:
        issue_invoice(inv, send_email=False)
        fail("re-issue should fail")
    except InvoiceFlowError:
        ok("re-issue blocked")

    from erp_core.invoice_pdf_html import generate_invoice_pdf_from_html

    pdf = generate_invoice_pdf_from_html(inv)
    if not pdf or len(pdf) < 100:
        fail(f"PDF empty or too small: {None if pdf is None else len(pdf)}")
    if not pdf[:4] == b"%PDF":
        fail("PDF missing %PDF header")
    ok(f"PDF generated ({len(pdf)} bytes)")

    print("\nINVOICE FLOW E2E PASSED")


if __name__ == "__main__":
    main()
