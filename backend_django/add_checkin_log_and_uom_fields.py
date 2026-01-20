"""
Add CheckInLog table and unit_of_measure fields to existing log tables using raw SQL
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.db import connection

def add_checkin_log_table():
    """Create CheckInLog table"""
    with connection.cursor() as cursor:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_checkinlog'")
        if cursor.fetchone():
            print("CheckInLog table already exists")
            return
        
        # Create table
        cursor.execute("""
            CREATE TABLE erp_core_checkinlog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id INTEGER REFERENCES erp_core_lot(id) ON DELETE SET NULL,
                lot_number VARCHAR(100) NOT NULL,
                item_id INTEGER,
                item_sku VARCHAR(255) NOT NULL,
                item_name VARCHAR(255) NOT NULL,
                item_type VARCHAR(50) NOT NULL,
                item_unit_of_measure VARCHAR(10) NOT NULL,
                po_number VARCHAR(100),
                vendor_name VARCHAR(255),
                received_date DATETIME NOT NULL,
                vendor_lot_number VARCHAR(100),
                quantity REAL NOT NULL,
                quantity_unit VARCHAR(10) NOT NULL DEFAULT 'lbs',
                status VARCHAR(20) NOT NULL DEFAULT 'accepted',
                short_reason TEXT,
                coa BOOLEAN NOT NULL DEFAULT 0,
                prod_free_pests BOOLEAN NOT NULL DEFAULT 0,
                carrier_free_pests BOOLEAN NOT NULL DEFAULT 0,
                shipment_accepted BOOLEAN NOT NULL DEFAULT 0,
                initials VARCHAR(50),
                carrier VARCHAR(255),
                freight_actual REAL,
                notes TEXT,
                checked_in_at DATETIME NOT NULL,
                checked_in_by VARCHAR(255)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX erp_core_checkinlog_checked_in_at_idx ON erp_core_checkinlog(checked_in_at DESC)")
        cursor.execute("CREATE INDEX erp_core_checkinlog_item_sku_checked_in_at_idx ON erp_core_checkinlog(item_sku, checked_in_at DESC)")
        cursor.execute("CREATE INDEX erp_core_checkinlog_po_number_checked_in_at_idx ON erp_core_checkinlog(po_number, checked_in_at DESC)")
        cursor.execute("CREATE INDEX erp_core_checkinlog_lot_number_checked_in_at_idx ON erp_core_checkinlog(lot_number, checked_in_at DESC)")
        
        print("CheckInLog table created successfully")

def add_uom_to_lottransactionlog():
    """Add unit_of_measure to LotTransactionLog"""
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(erp_core_lottransactionlog)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'unit_of_measure' not in columns:
            cursor.execute("ALTER TABLE erp_core_lottransactionlog ADD COLUMN unit_of_measure VARCHAR(10) NOT NULL DEFAULT 'lbs'")
            print("Added unit_of_measure to LotTransactionLog")
        else:
            print("unit_of_measure already exists in LotTransactionLog")

def add_uom_to_lotdepletionlog():
    """Add unit_of_measure to LotDepletionLog"""
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(erp_core_lotdepletionlog)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'unit_of_measure' not in columns:
            cursor.execute("ALTER TABLE erp_core_lotdepletionlog ADD COLUMN unit_of_measure VARCHAR(10) NOT NULL DEFAULT 'lbs'")
            print("Added unit_of_measure to LotDepletionLog")
        else:
            print("unit_of_measure already exists in LotDepletionLog")

def add_uom_to_productionlog():
    """Add unit_of_measure to ProductionLog"""
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(erp_core_productionlog)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'unit_of_measure' not in columns:
            cursor.execute("ALTER TABLE erp_core_productionlog ADD COLUMN unit_of_measure VARCHAR(10) NOT NULL DEFAULT 'lbs'")
            print("Added unit_of_measure to ProductionLog")
        else:
            print("unit_of_measure already exists in ProductionLog")

def main():
    print("="*80)
    print("ADDING CHECK-IN LOG AND UOM FIELDS")
    print("="*80)
    
    try:
        add_checkin_log_table()
        add_uom_to_lottransactionlog()
        add_uom_to_lotdepletionlog()
        add_uom_to_productionlog()
        
        print("\n" + "="*80)
        print("SUCCESS: All changes applied")
        print("="*80)
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
