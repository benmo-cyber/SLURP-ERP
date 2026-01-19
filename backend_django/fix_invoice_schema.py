"""
Fix Invoice schema by adding missing columns
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

def fix_invoice_schema():
    """Add missing columns to Invoice table"""
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(erp_core_invoice)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        # Add missing columns
        if 'freight' not in columns:
            print("Adding 'freight' column...")
            cursor.execute("ALTER TABLE erp_core_invoice ADD COLUMN freight REAL DEFAULT 0.0")
            print("  [OK] Added freight column")
        else:
            print("  [SKIP] freight column already exists")
        
        if 'tax' not in columns:
            print("Adding 'tax' column...")
            cursor.execute("ALTER TABLE erp_core_invoice ADD COLUMN tax REAL DEFAULT 0.0")
            print("  [OK] Added tax column")
        else:
            print("  [SKIP] tax column already exists")
        
        if 'discount' not in columns:
            print("Adding 'discount' column...")
            cursor.execute("ALTER TABLE erp_core_invoice ADD COLUMN discount REAL DEFAULT 0.0")
            print("  [OK] Added discount column")
        else:
            print("  [SKIP] discount column already exists")
        
        if 'grand_total' not in columns:
            print("Adding 'grand_total' column...")
            cursor.execute("ALTER TABLE erp_core_invoice ADD COLUMN grand_total REAL DEFAULT 0.0")
            print("  [OK] Added grand_total column")
        else:
            print("  [SKIP] grand_total column already exists")
        
        conn.commit()
        print("\n[DONE] Invoice schema fixed successfully!")
        
    except Exception as e:
        print(f"\n[ERROR] Failed to fix schema: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_invoice_schema()
