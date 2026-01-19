"""
Script to clear invoice test data
"""
import os
import sys
import django
from pathlib import Path
import sqlite3

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.conf import settings
from erp_core.models import Invoice, InvoiceItem

def clear_invoice_data():
    """Clear all invoice data"""
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Delete invoice items first (foreign key constraint)
        try:
            cursor.execute("DELETE FROM erp_core_invoiceitem")
            print(f"  [OK] Deleted all invoice items")
        except Exception as e:
            print(f"  [SKIP] Could not delete invoice items: {e}")
        
        # Delete invoices
        try:
            cursor.execute("DELETE FROM erp_core_invoice")
            print(f"  [OK] Deleted all invoices")
        except Exception as e:
            print(f"  [SKIP] Could not delete invoices: {e}")
        
        conn.commit()
        print("\n[DONE] Invoice data cleared successfully")
        
    except Exception as e:
        print(f"  [ERROR] Failed to clear invoice data: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("Clearing invoice test data...")
    clear_invoice_data()
