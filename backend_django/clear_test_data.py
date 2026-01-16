#!/usr/bin/env python
"""
Script to clear all test data from SLURP database.
This will delete all records from all models except system tables.
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import (
    Item, Lot, ProductionBatch, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, LotNumberSequence, Vendor, VendorHistory,
    SupplierSurvey, SupplierDocument, TemporaryException, CostMaster,
    PONumberSequence, SalesOrderNumberSequence, InvoiceNumberSequence,
    CustomerNumberSequence, ProductionBatchInput, ProductionBatchOutput, Account, CostMasterHistory,
    FinishedProductSpecification, Customer, CustomerPricing, SalesOrderLot
)

def clear_all_data():
    """Delete all data from all models."""
    print("Clearing all test data from SLURP...")
    print("-" * 50)
    
    # Delete in reverse order of dependencies to handle foreign keys
    # Inventory data must be cleared first (transactions, then lots, then items)
    models_to_clear = [
        ("Sales Order Lots", SalesOrderLot),
        ("Customer Pricing", CustomerPricing),
        ("Customers", Customer),
        ("Inventory Transactions", InventoryTransaction),  # Must be before Lots
        ("Sales Order Items", SalesOrderItem),
        ("Sales Orders", SalesOrder),
        ("Purchase Order Items", PurchaseOrderItem),
        ("Purchase Orders", PurchaseOrder),
        ("Production Batch Outputs", ProductionBatchOutput),
        ("Production Batch Inputs", ProductionBatchInput),
        ("Production Batches", ProductionBatch),
        ("Formula Items", FormulaItem),
        ("Formulas", Formula),
        ("Finished Product Specifications", FinishedProductSpecification),
        ("Temporary Exceptions", TemporaryException),
        ("Supplier Documents", SupplierDocument),
        ("Supplier Surveys", SupplierSurvey),
        ("Vendor History", VendorHistory),
        ("Vendors", Vendor),
        ("Cost Master History", CostMasterHistory),
        ("Cost Master", CostMaster),
        # NOTE: Accounts are NOT cleared - they are part of the Chart of Accounts
        # ("Accounts", Account),  # PROTECTED - Chart of Accounts should not be cleared
        ("Lots", Lot),  # Must be before Items
        ("Items", Item),  # Base inventory model
    ]
    
    total_deleted = 0
    
    from django.db import connection, transaction
    
    for name, model in models_to_clear:
        try:
            # For Items and Lots, handle cascade deletion issues with non-existent tables
            if name in ['Items', 'Lots']:
                try:
                    count = model.objects.all().count()
                    if count > 0:
                        # Use raw SQL to delete and avoid cascade to non-existent tables
                        table_name = model._meta.db_table
                        with connection.cursor() as cursor:
                            # Disable foreign key checks for SQLite
                            cursor.execute("PRAGMA foreign_keys=OFF")
                            # Delete all records
                            cursor.execute(f'DELETE FROM "{table_name}"')
                            cursor.execute("PRAGMA foreign_keys=ON")
                        print(f"[OK] Deleted {count} {name}")
                        total_deleted += count
                    else:
                        print(f"  No {name} to delete")
                except Exception as delete_error:
                    error_msg = str(delete_error)
                    if 'no such table' in error_msg.lower():
                        print(f"  [SKIP] {name} - table does not exist")
                    elif 'salesorderlot' in error_msg.lower():
                        # Try raw SQL deletion to bypass cascade
                        try:
                            table_name = model._meta.db_table
                            with connection.cursor() as cursor:
                                cursor.execute("PRAGMA foreign_keys=OFF")
                                cursor.execute(f'DELETE FROM "{table_name}"')
                                cursor.execute("PRAGMA foreign_keys=ON")
                            print(f"[OK] Deleted {name} using raw SQL (bypassed cascade)")
                        except:
                            print(f"  [SKIP] {name} - {error_msg[:100]}")
                    else:
                        print(f"  [SKIP] {name} - {error_msg[:100]}")
            else:
                # For other models, use ORM
                count = model.objects.all().count()
                if count > 0:
                    model.objects.all().delete()
                    print(f"[OK] Deleted {count} {name}")
                    total_deleted += count
                else:
                    print(f"  No {name} to delete")
        except Exception as e:
            error_msg = str(e)
            # Check if it's a "table doesn't exist" error
            if 'no such table' in error_msg.lower() or 'does not exist' in error_msg.lower():
                print(f"  [SKIP] {name} - table does not exist")
            else:
                print(f"  [SKIP] {name} - {error_msg[:100]}")
    
    # Reset all number sequences to 0
    print("-" * 50)
    print("Resetting number sequences...")
    
    sequences_to_reset = [
        ("Lot Number Sequences", LotNumberSequence),
        ("PO Number Sequences", PONumberSequence),
        ("Sales Order Number Sequences", SalesOrderNumberSequence),
        ("Invoice Number Sequences", InvoiceNumberSequence),
        ("Customer Number Sequences", CustomerNumberSequence),
    ]
    
    for name, model in sequences_to_reset:
        try:
            count = model.objects.all().count()
            if count > 0:
                model.objects.all().update(sequence_number=0)
                print(f"[OK] Reset {count} {name} to sequence 0")
            else:
                print(f"  No {name} to reset")
        except Exception as e:
            print(f"  [SKIP] {name} - {str(e)}")
    
    print("-" * 50)
    print(f"[OK] Cleared {total_deleted} total records")
    print("[OK] All test data has been cleared and sequences reset!")

if __name__ == '__main__':
    # Auto-confirm for script usage
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--yes':
        clear_all_data()
    else:
        confirm = input("Are you sure you want to delete ALL data? Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            clear_all_data()
        else:
            print("Cancelled. No data was deleted.")

