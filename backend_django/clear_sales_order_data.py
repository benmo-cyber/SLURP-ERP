"""
Script to clear all sales order data
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

from django.db import connection
from erp_core.models import (
    SalesOrderLot, SalesOrderItem, SalesOrder,
    ShipmentItem, Shipment,
    InvoiceItem, Invoice,
    AccountsReceivable  # AR entries tied to invoices
)
import sqlite3

def safe_delete(model_class, description):
    """Safely delete all records from a model"""
    try:
        count = model_class.objects.all().count()
        if count > 0:
            model_class.objects.all().delete()
            print(f"  [OK] Deleted {count} {description}")
        else:
            print(f"  [OK] No {description} to delete")
    except Exception as e:
        print(f"  [ERROR] Could not delete {description}: {e}")

def safe_delete_raw_sql(table_name, description):
    """Delete all records from a table using raw SQL"""
    from django.conf import settings
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [table_name]
        )
        if not cursor.fetchone():
            print(f"  [SKIP] Table {table_name} does not exist")
            return
        
        # Get count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Delete all records
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            print(f"  [OK] Deleted {count} {description}")
        else:
            print(f"  [OK] No {description} to delete")
    except Exception as e:
        print(f"  [ERROR] Could not delete {description}: {e}")
        conn.rollback()
    finally:
        conn.close()

def clear_sales_order_data():
    """Clear all sales order related data"""
    print("Clearing sales order data...")
    
    # Clear in order of dependencies (child records first)
    print("  - Clearing sales order allocations and items...")
    safe_delete(SalesOrderLot, "sales order lot allocations")
    safe_delete(ShipmentItem, "shipment items")
    safe_delete(Shipment, "shipments")
    
    # Use raw SQL to bypass schema issues
    safe_delete_raw_sql("erp_core_salesorderitem", "sales order items")
    safe_delete_raw_sql("erp_core_salesorder", "sales orders")
    
    # Clear invoices (which may be tied to sales orders)
    print("  - Clearing invoices...")
    safe_delete(InvoiceItem, "invoice items")
    safe_delete(Invoice, "invoices")
    
    # Clear AR entries (which are tied to invoices)
    print("  - Clearing accounts receivable entries...")
    safe_delete(AccountsReceivable, "accounts receivable entries")
    
    print("  [OK] Sales order data cleared")

if __name__ == '__main__':
    print("="*60)
    print("CLEARING SALES ORDER DATA")
    print("="*60)
    
    clear_sales_order_data()
    
    print("\n" + "="*60)
    print("[DONE] Sales order data cleared successfully!")
    print("="*60)
