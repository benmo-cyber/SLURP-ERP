"""
Script to add vendor address fields directly to database
Run this to add the new address fields without migrations
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

def add_vendor_address_fields():
    """Add separate address fields to Vendor table"""
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if fields already exist
        cursor.execute("PRAGMA table_info(erp_core_vendor)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'street_address' not in columns:
            cursor.execute("ALTER TABLE erp_core_vendor ADD COLUMN street_address VARCHAR(255) NULL")
            print("  [OK] Added street_address column")
        else:
            print("  [SKIP] street_address column already exists")
            
        if 'city' not in columns:
            cursor.execute("ALTER TABLE erp_core_vendor ADD COLUMN city VARCHAR(100) NULL")
            print("  [OK] Added city column")
        else:
            print("  [SKIP] city column already exists")
            
        if 'state' not in columns:
            cursor.execute("ALTER TABLE erp_core_vendor ADD COLUMN state VARCHAR(50) NULL")
            print("  [OK] Added state column")
        else:
            print("  [SKIP] state column already exists")
            
        if 'zip_code' not in columns:
            cursor.execute("ALTER TABLE erp_core_vendor ADD COLUMN zip_code VARCHAR(20) NULL")
            print("  [OK] Added zip_code column")
        else:
            print("  [SKIP] zip_code column already exists")
            
        if 'country' not in columns:
            cursor.execute("ALTER TABLE erp_core_vendor ADD COLUMN country VARCHAR(100) NULL DEFAULT 'USA'")
            print("  [OK] Added country column")
        else:
            print("  [SKIP] country column already exists")
        
        conn.commit()
        print("\n[DONE] Vendor address fields added successfully")
        
    except Exception as e:
        print(f"  [ERROR] Failed to add vendor address fields: {e}")
        conn.rollback()
    finally:
        conn.close()

def add_item_hts_fields():
    """Add HTS code and country of origin fields to Item table"""
    db_path = settings.DATABASES['default']['NAME']
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if fields already exist
        cursor.execute("PRAGMA table_info(erp_core_item)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'hts_code' not in columns:
            cursor.execute("ALTER TABLE erp_core_item ADD COLUMN hts_code VARCHAR(50) NULL")
            print("  [OK] Added hts_code column")
        else:
            print("  [SKIP] hts_code column already exists")
            
        if 'country_of_origin' not in columns:
            cursor.execute("ALTER TABLE erp_core_item ADD COLUMN country_of_origin VARCHAR(255) NULL")
            print("  [OK] Added country_of_origin column")
        else:
            print("  [SKIP] country_of_origin column already exists")
        
        conn.commit()
        print("\n[DONE] Item HTS fields added successfully")
        
    except Exception as e:
        print(f"  [ERROR] Failed to add item HTS fields: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("Adding vendor address fields...")
    add_vendor_address_fields()
    
    print("\nAdding item HTS fields...")
    add_item_hts_fields()
    
    print("\n[COMPLETE] All database fields added")
