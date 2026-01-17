#!/usr/bin/env python
"""Script to manually apply migrations that are blocked by migration dependency issues"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'wwi_erp.db')

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if vendor_item_name column already exists
    cursor.execute("PRAGMA table_info(erp_core_item)")
    cols = [row[1] for row in cursor.fetchall()]
    
    if 'vendor_item_name' in cols:
        print("Column vendor_item_name already exists")
    else:
        # Add vendor_item_name column
        cursor.execute('ALTER TABLE erp_core_item ADD COLUMN vendor_item_name VARCHAR(255) NULL')
        conn.commit()
        print("Successfully added vendor_item_name column to erp_core_item")
    
    # Check if LotTransactionLog table exists and update transaction types
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_lottransactionlog'")
    if cursor.fetchone():
        print("LotTransactionLog table exists - transaction types will be updated when migration runs")
    else:
        print("LotTransactionLog table does not exist yet")
    
    # Check InventoryTransaction table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_inventorytransaction'")
    if cursor.fetchone():
        print("InventoryTransaction table exists - transaction types will be updated when migration runs")
    else:
        print("InventoryTransaction table does not exist yet")
    
    print("\nMigration changes applied successfully!")
    print("Note: Transaction type changes will be applied via Django migration when the dependency issue is resolved")
    
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
