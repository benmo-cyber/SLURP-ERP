#!/usr/bin/env python
"""Script to manually apply orphaned inventory migration"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'wwi_erp.db')

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if OrphanedInventory table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_orphanedinventory'")
    if cursor.fetchone():
        print("OrphanedInventory table already exists")
    else:
        # Create OrphanedInventory table
        cursor.execute("""
            CREATE TABLE "erp_core_orphanedinventory" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "original_item_sku" varchar(255) NOT NULL,
                "original_item_name" varchar(255) NOT NULL,
                "original_item_vendor" varchar(255) NULL,
                "original_item_type" varchar(50) NOT NULL,
                "original_item_unit" varchar(10) NOT NULL,
                "lot_number" varchar(20) NOT NULL UNIQUE,
                "vendor_lot_number" varchar(100) NULL,
                "quantity" real NOT NULL,
                "quantity_remaining" real NOT NULL,
                "received_date" datetime NOT NULL,
                "expiration_date" datetime NULL,
                "status" varchar(20) NOT NULL,
                "po_number" varchar(100) NULL,
                "freight_actual" real NULL,
                "short_reason" varchar(255) NULL,
                "reassigned_at" datetime NULL,
                "reassigned_by" varchar(255) NULL,
                "created_at" datetime NOT NULL,
                "notes" text NULL,
                "reassigned_item_id" integer NULL REFERENCES "erp_core_item" ("id") DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX erp_core_orphanedinventory_original_item_sku ON erp_core_orphanedinventory (original_item_sku)")
        cursor.execute("CREATE INDEX erp_core_orphanedinventory_lot_number ON erp_core_orphanedinventory (lot_number)")
        print("Successfully created OrphanedInventory table")
    
    # Check if OrphanedPurchaseOrderItem table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_orphanedpurchaseorderitem'")
    if cursor.fetchone():
        print("OrphanedPurchaseOrderItem table already exists")
    else:
        # Create OrphanedPurchaseOrderItem table
        cursor.execute("""
            CREATE TABLE "erp_core_orphanedpurchaseorderitem" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                "original_item_sku" varchar(255) NOT NULL,
                "original_item_name" varchar(255) NOT NULL,
                "original_item_vendor" varchar(255) NULL,
                "original_item_unit" varchar(10) NOT NULL,
                "quantity_ordered" real NOT NULL,
                "quantity_received" real NOT NULL,
                "unit_price" real NULL,
                "notes" text NULL,
                "reassigned_at" datetime NULL,
                "reassigned_by" varchar(255) NULL,
                "created_at" datetime NOT NULL,
                "purchase_order_id" integer NOT NULL REFERENCES "erp_core_purchaseorder" ("id") DEFERRABLE INITIALLY DEFERRED,
                "reassigned_item_id" integer NULL REFERENCES "erp_core_item" ("id") DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX erp_core_orphanedpurchaseorderitem_original_item_sku ON erp_core_orphanedpurchaseorderitem (original_item_sku)")
        print("Successfully created OrphanedPurchaseOrderItem table")
    
    conn.commit()
    print("\nOrphaned inventory migration applied successfully!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.close()
