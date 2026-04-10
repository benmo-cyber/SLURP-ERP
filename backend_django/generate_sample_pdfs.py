"""
Script to generate sample PDFs for purchase orders, invoices, and sales orders
Uses existing records from the database
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import PurchaseOrder, SalesOrder, Invoice
from erp_core.po_pdf_html import generate_po_pdf_from_html
from erp_core.invoice_pdf_html import generate_invoice_pdf_from_html
from erp_core.sales_order_pdf_html import generate_sales_order_pdf_from_html
import tempfile
import subprocess

def main():
    print("Finding existing records...")
    
    # Find existing purchase order
    po = PurchaseOrder.objects.filter(status__in=['issued', 'draft']).first()
    if not po:
        po = PurchaseOrder.objects.first()
    
    # Find existing sales order
    so = SalesOrder.objects.filter(status__in=['issued', 'draft']).first()
    if not so:
        so = SalesOrder.objects.first()
    
    # Find existing invoice (handle schema mismatches)
    invoice = None
    try:
        invoice = Invoice.objects.filter(status__in=['sent', 'draft']).first()
        if not invoice:
            invoice = Invoice.objects.first()
    except Exception:
        # Schema mismatch - skip invoices
        invoice = None
    
    if not po and not so and not invoice:
        print("[ERROR] No records found in database. Please create at least one purchase order, sales order, or invoice first.")
        return
    
    # Create temp directory for PDFs
    temp_dir = tempfile.mkdtemp()
    print(f"\nGenerating PDFs in: {temp_dir}\n")
    
    pdfs_to_open = []
    
    # Generate Purchase Order PDF
    if po:
        print(f"Generating purchase order PDF for {po.po_number}...")
        try:
            po_pdf = generate_po_pdf_from_html(po)
            if not po_pdf:
                print(f"  [ERROR] PO HTML PDF returned no data")
                raise RuntimeError("PO PDF failed")
            po_path = os.path.join(temp_dir, f"Purchase_Order_{po.po_number}.pdf")
            with open(po_path, 'wb') as f:
                f.write(po_pdf)
            print(f"  [OK] Saved: {po_path}")
            pdfs_to_open.append(po_path)
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("  [SKIP] No purchase order found")
    
    # Generate Sales Order PDF
    if so:
        print(f"\nGenerating sales order PDF for {so.so_number}...")
        try:
            so_pdf = generate_sales_order_pdf_from_html(so)
            so_path = os.path.join(temp_dir, f"Sales_Order_{so.so_number}.pdf")
            with open(so_path, 'wb') as f:
                f.write(so_pdf)
            print(f"  [OK] Saved: {so_path}")
            pdfs_to_open.append(so_path)
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n  [SKIP] No sales order found")
    
    # Generate Invoice PDF
    if invoice:
        print(f"\nGenerating invoice PDF for {invoice.invoice_number}...")
        try:
            invoice_pdf = generate_invoice_pdf_from_html(invoice)
            if not invoice_pdf:
                print(f"  [ERROR] Invoice HTML PDF returned no data")
                raise RuntimeError("Invoice PDF failed")
            invoice_path = os.path.join(temp_dir, f"Invoice_{invoice.invoice_number}.pdf")
            with open(invoice_path, 'wb') as f:
                f.write(invoice_pdf)
            print(f"  [OK] Saved: {invoice_path}")
            pdfs_to_open.append(invoice_path)
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n  [SKIP] No invoice found")
    
    # Open PDFs in Chrome
    if pdfs_to_open:
        print(f"\nOpening {len(pdfs_to_open)} PDF(s) in Chrome...")
        try:
            # Windows: use start command with chrome
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            if not os.path.exists(chrome_path):
                chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            
            if os.path.exists(chrome_path):
                for pdf_path in pdfs_to_open:
                    subprocess.Popen([chrome_path, pdf_path])
                print(f"  [OK] Opened {len(pdfs_to_open)} PDF(s) in Chrome")
            else:
                # Fallback: use default PDF viewer
                for pdf_path in pdfs_to_open:
                    os.startfile(pdf_path)
                print(f"  [OK] Opened {len(pdfs_to_open)} PDF(s) with default viewer")
        except Exception as e:
            print(f"  [ERROR] Error opening PDFs: {e}")
            print(f"  You can manually open:")
            for pdf_path in pdfs_to_open:
                print(f"    - {pdf_path}")
    else:
        print("\n[ERROR] No PDFs were generated successfully")
    
    print("\n[DONE]")

if __name__ == '__main__':
    main()
