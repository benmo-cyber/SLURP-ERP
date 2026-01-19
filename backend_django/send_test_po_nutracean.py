"""
Script to send a test purchase order to Nutracean
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

from erp_core.models import Vendor, PurchaseOrder
from erp_core.email_service import send_purchase_order_email
from erp_core.pdf_generator import generate_purchase_order_pdf
from django.utils import timezone
from datetime import timedelta

def send_test_po_to_nutracean():
    """Find Nutracean vendor and send a test purchase order"""
    
    # Find Nutracean vendor
    try:
        vendor = Vendor.objects.filter(name__icontains='Nutracean').first()
        if not vendor:
            print("ERROR: Nutracean vendor not found in database")
            print("Available vendors:")
            for v in Vendor.objects.all()[:10]:
                print(f"  - {v.name}")
            return False
        
        print(f"Found vendor: {vendor.name}")
        print(f"Email: {vendor.email}")
        print(f"Contact: {vendor.contact_name}")
        
        if not vendor.email:
            print("ERROR: Nutracean vendor does not have an email address on file")
            return False
        
        # Find an existing purchase order for Nutracean
        po = PurchaseOrder.objects.filter(vendor_customer_name=vendor.name).order_by('-po_number').first()
        
        if not po:
            print("No existing purchase order found for Nutracean")
            print("Creating a test purchase order...")
            
            # Generate PO number
            from erp_core.views import generate_po_number
            po_number = generate_po_number()
            
            # Create a test purchase order
            po = PurchaseOrder.objects.create(
                po_number=po_number,
                vendor_customer_name=vendor.name,
                vendor_customer_id=str(vendor.id),
                expected_delivery_date=(timezone.now() + timedelta(days=30)).date(),
                status='issued',
                vendor_address=vendor.street_address or '',
                vendor_city=vendor.city or '',
                vendor_state=vendor.state or '',
                vendor_zip=vendor.zip_code or '',
                vendor_country=vendor.country or 'USA',
            )
            print(f"Created test purchase order: {po.po_number}")
        else:
            print(f"Using existing purchase order: {po.po_number}")
        
        # Generate PDF
        print("Generating PDF...")
        pdf_content = generate_purchase_order_pdf(po)
        
        # Save PDF to file as backup
        pdf_path = BASE_DIR / f"Purchase_Order_{po.po_number}.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        print(f"PDF saved to: {pdf_path}")
        
        # Send email
        print(f"Sending email to {vendor.email}...")
        success = send_purchase_order_email(po, pdf_content)
        
        if success:
            print(f"SUCCESS: Purchase order {po.po_number} sent to {vendor.email}")
            return True
        else:
            print("WARNING: Failed to send purchase order email")
            print(f"  The PDF has been saved to: {pdf_path}")
            print(f"  You can manually send it to {vendor.email}")
            print("  Note: SMTP authentication may need to be enabled in Microsoft 365 admin center")
            return False
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    send_test_po_to_nutracean()
