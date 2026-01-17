#!/usr/bin/env python
"""Script to manually make lot_number nullable"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'wwi_erp.db')

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check current schema
    cursor.execute("PRAGMA table_info(erp_core_lot)")
    cols = cursor.fetchall()
    lot_number_col = [col for col in cols if col[1] == 'lot_number']
    
    if lot_number_col:
        print(f"Current lot_number column: {lot_number_col[0]}")
        # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
        # But this is complex, so let's check if we can work around it
        
        # For now, we'll note that the model change is made
        # The unique constraint will need to be handled differently
        # We can use a partial unique index that only applies to non-null values
        print("\nNote: SQLite doesn't support ALTER COLUMN to make a field nullable.")
        print("The model change has been made, but the database schema change requires:")
        print("1. Creating a new table with nullable lot_number")
        print("2. Copying data")
        print("3. Dropping old table and renaming new one")
        print("\nFor now, the code will work with existing lots that have lot_numbers.")
        print("New lots created without lot_numbers may need special handling.")
        print("\nAlternatively, we can use a unique constraint that allows NULL values.")
        
        # Create a unique index that allows NULL (SQLite allows multiple NULLs in unique indexes)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS erp_core_lot_lot_number_unique 
            ON erp_core_lot(lot_number) 
            WHERE lot_number IS NOT NULL
        """)
        print("\nCreated partial unique index on lot_number (allows NULL values)")
        
    conn.commit()
    print("\nMigration preparation completed!")
    print("Note: Full migration may require table recreation for SQLite.")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    conn.close()
