"""
Script to clear inventory and items data using raw SQL
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
from django.conf import settings
import sqlite3

def clear_inventory_and_items():
    """Clear all inventory and items data using raw SQL"""
    print("Clearing inventory and items data...")
    
    # Get database path
    db_path = settings.DATABASES['default']['NAME']
    
    tables_to_clear = [
        ("erp_core_lottransactionlog", "lot transaction logs"),
        ("erp_core_inventorytransaction", "inventory transactions"),
        ("erp_core_lot", "lots"),
        ("erp_core_itempacksize", "item pack sizes"),
        ("erp_core_item", "items"),
    ]
    
    # Use direct sqlite3 connection to bypass Django's query formatting
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for table_name, description in tables_to_clear:
            try:
                # Check if table exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    [table_name]
                )
                if not cursor.fetchone():
                    print(f"  [SKIP] Table {table_name} does not exist")
                    continue
                
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
    
    print("\n[DONE] Inventory and items data cleared")

if __name__ == '__main__':
    clear_inventory_and_items()
