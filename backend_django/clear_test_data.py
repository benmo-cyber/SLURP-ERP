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
    SupplierSurvey, SupplierDocument, TemporaryException, CostMaster
)

def clear_all_data():
    """Delete all data from all models."""
    print("Clearing all test data from SLURP...")
    print("-" * 50)
    
    # Delete in reverse order of dependencies
    models_to_clear = [
        ("Inventory Transactions", InventoryTransaction),
        ("Sales Order Items", SalesOrderItem),
        ("Sales Orders", SalesOrder),
        ("Purchase Order Items", PurchaseOrderItem),
        ("Purchase Orders", PurchaseOrder),
        ("Production Batches", ProductionBatch),
        ("Formula Items", FormulaItem),
        ("Formulas", Formula),
        ("Lots", Lot),
        ("Lot Number Sequences", LotNumberSequence),
        ("Temporary Exceptions", TemporaryException),
        ("Supplier Documents", SupplierDocument),
        ("Supplier Surveys", SupplierSurvey),
        ("Vendor History", VendorHistory),
        ("Vendors", Vendor),
        ("Cost Master", CostMaster),
        ("Items", Item),
    ]
    
    total_deleted = 0
    
    for name, model in models_to_clear:
        count = model.objects.all().count()
        if count > 0:
            model.objects.all().delete()
            print(f"[OK] Deleted {count} {name}")
            total_deleted += count
        else:
            print(f"  No {name} to delete")
    
    print("-" * 50)
    print(f"[OK] Cleared {total_deleted} total records")
    print("[OK] All test data has been cleared!")

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

