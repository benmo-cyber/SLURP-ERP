"""
Script to clear inventory table data, items management data, and calendar data
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
    LotTransactionLog, InventoryTransaction, Lot, ItemPackSize, Item,
    SalesCall  # Calendar data
)
import sqlite3

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

def clear_inventory_and_items():
    """Clear inventory table data and items management data"""
    print("Clearing inventory table data and items management data...")
    
    # Clear in order of dependencies
    safe_delete_raw_sql("erp_core_lottransactionlog", "lot transaction logs")
    safe_delete_raw_sql("erp_core_inventorytransaction", "inventory transactions")
    safe_delete_raw_sql("erp_core_lot", "lots")
    safe_delete_raw_sql("erp_core_itempacksize", "item pack sizes")
    safe_delete_raw_sql("erp_core_item", "items")
    
    print("  [OK] Inventory and items data cleared")

def clear_calendar_data():
    """Clear calendar data (sales calls)"""
    print("Clearing calendar data...")
    
    try:
        count = SalesCall.objects.all().count()
        if count > 0:
            SalesCall.objects.all().delete()
            print(f"  [OK] Deleted {count} sales calls")
        else:
            print(f"  [OK] No sales calls to delete")
    except Exception as e:
        print(f"  [ERROR] Could not delete sales calls: {e}")
        # Try raw SQL
        safe_delete_raw_sql("erp_core_salescall", "sales calls")
    
    print("  [OK] Calendar data cleared")

if __name__ == '__main__':
    print("="*60)
    print("CLEARING INVENTORY, ITEMS, AND CALENDAR DATA")
    print("="*60)
    
    clear_inventory_and_items()
    print()
    clear_calendar_data()
    
    print("\n" + "="*60)
    print("[DONE] Data cleared successfully!")
    print("="*60)
