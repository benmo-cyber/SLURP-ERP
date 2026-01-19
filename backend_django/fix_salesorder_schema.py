"""
Fix SalesOrder schema if needed
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

def fix_salesorder_schema():
    """Add missing columns to SalesOrder table if needed"""
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(erp_core_salesorder)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        # Add missing columns with defaults if they're NOT NULL
        if 'discount' in columns and columns['discount'][3] == 1:  # NOT NULL
            # Column exists and is NOT NULL, update NULL values to 0
            cursor.execute("UPDATE erp_core_salesorder SET discount = 0.0 WHERE discount IS NULL")
            print("  [OK] Updated NULL discount values to 0.0")
        
        conn.commit()
        print("\n[DONE] SalesOrder schema checked!")
        
    except Exception as e:
        print(f"\n[ERROR] Failed to fix schema: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_salesorder_schema()
