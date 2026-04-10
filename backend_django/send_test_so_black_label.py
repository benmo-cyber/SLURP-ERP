"""
Script to send a test sales order confirmation email as if a Black Label order was issued.
"""
import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')

import django
django.setup()

from erp_core.models import SalesOrder, Customer
from erp_core.email_service import send_sales_order_confirmation_email
from erp_core.sales_order_pdf_html import generate_sales_order_pdf_from_html


def send_test_so_confirmation_black_label():
    """Find a sales order for Black Label and send confirmation email (or use first SO if none)."""
    # Prefer: customer name contains "Black Label"
    customer = Customer.objects.filter(name__icontains='Black Label').first()
    if customer:
        sales_order = (
            SalesOrder.objects.filter(customer=customer)
            .prefetch_related('items', 'items__item')
            .order_by('-id')
            .first()
        )
        if not sales_order:
            sales_order = (
                SalesOrder.objects.filter(customer_name__icontains='Black Label')
                .prefetch_related('items', 'items__item')
                .order_by('-id')
                .first()
            )
    else:
        sales_order = None

    if not sales_order:
        # Fallback: any sales order (for testing email/PDF)
        sales_order = (
            SalesOrder.objects.all()
            .select_related('customer', 'ship_to_location')
            .prefetch_related('items', 'items__item')
            .order_by('-id')
            .first()
        )
        if not sales_order:
            print("ERROR: No sales orders in database. Create a sales order first.")
            return False
        print("Note: No customer named 'Black Label' found. Using most recent sales order for test.")
        print(f"  SO: {sales_order.so_number} | Customer: {sales_order.customer_name or (sales_order.customer.name if sales_order.customer else 'N/A')}")
    else:
        print(f"Found sales order for Black Label: {sales_order.so_number}")

    print(f"Generating PDF for SO {sales_order.so_number}...")
    pdf_content = generate_sales_order_pdf_from_html(sales_order)
    print(f"Sending confirmation email (recipients from purchasing contacts / customer / ship-to)...")
    ok = send_sales_order_confirmation_email(sales_order, pdf_content)
    if ok:
        print("Done. Sales order confirmation email sent successfully.")
    else:
        print("Email was not sent (no recipient email found for this order).")
    return ok


if __name__ == '__main__':
    send_test_so_confirmation_black_label()
