"""
Script to clear all test data and reset number generation sequences
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

from django.db import transaction
from django.utils import timezone
from erp_core.models import (
    # Sequences
    LotNumberSequence, PONumberSequence, SalesOrderNumberSequence,
    InvoiceNumberSequence, CustomerNumberSequence, BatchNumberSequence,
    # Transactions and Orders
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    Invoice, InvoiceItem, Shipment, ShipmentItem,
    # Production
    ProductionBatch, ProductionBatchInput, ProductionBatchOutput,
    # Inventory (to be cleared)
    Item, ItemPackSize, Lot, InventoryTransaction, LotTransactionLog,
    # Sales data (to be cleared)
    Customer, CustomerContact, CustomerForecast, CustomerPricing,
    ShipToLocation, SalesCall,
    # Quality data (to be cleared)
    SupplierSurvey, SupplierDocument, VendorHistory,
    # Other master data (to be cleared)
    Vendor, VendorPricing, Formula, FormulaItem,
    CostMaster, CostMasterHistory, FinishedProductSpecification,
    # Financial
    JournalEntry, JournalEntryLine, GeneralLedgerEntry, AccountBalance,
    AccountsPayable, AccountsReceivable, Payment,
    FiscalPeriod,
    # Other
    SalesOrderLot, PurchaseOrderLog, ProductionLog, LotDepletionLog,
    # Keep: Account (chart of accounts) - NOT imported for deletion
)

def safe_delete(model_class, description):
    """Safely delete all records from a model, handling schema mismatches"""
    try:
        count = model_class.objects.all().count()
        if count > 0:
            model_class.objects.all().delete()
            print(f"    Deleted {count} {description}")
        else:
            print(f"    No {description} to delete")
    except Exception as e:
        print(f"    [SKIP] Could not delete {description}: {e}")

def safe_delete_raw_sql(table_name, description):
    """Delete all records from a table using raw SQL to bypass ORM issues"""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute(f"DELETE FROM {table_name}")
                print(f"    Deleted {count} {description} (raw SQL)")
            else:
                print(f"    No {description} to delete")
    except Exception as e:
        print(f"    [SKIP] Could not delete {description}: {e}")

def clear_test_data():
    """Clear all test/transaction data"""
    print("Clearing test data...")
    
    # Don't use transaction.atomic() as schema mismatches can break the transaction
    # Financial transactions
    print("  - Clearing financial transactions...")
    safe_delete(Payment, "payments")
    safe_delete(AccountsReceivable, "accounts receivable entries")
    safe_delete(AccountsPayable, "accounts payable entries")
    safe_delete(GeneralLedgerEntry, "general ledger entries")
    safe_delete(AccountBalance, "account balances")
    safe_delete(JournalEntryLine, "journal entry lines")
    safe_delete(JournalEntry, "journal entries")
    safe_delete(FiscalPeriod, "fiscal periods")
    
    # Invoices and Sales Orders
    print("  - Clearing invoices and sales orders...")
    safe_delete(InvoiceItem, "invoice items")
    safe_delete(Invoice, "invoices")
    safe_delete(SalesOrderLot, "sales order lot allocations")
    safe_delete(SalesOrderItem, "sales order items")
    safe_delete(SalesOrder, "sales orders")
    safe_delete(ShipmentItem, "shipment items")
    safe_delete(Shipment, "shipments")
    
    # Purchase Orders
    print("  - Clearing purchase orders...")
    safe_delete(PurchaseOrderItem, "purchase order items")
    safe_delete(PurchaseOrder, "purchase orders")
    
    # Production
    print("  - Clearing production batches...")
    safe_delete(ProductionBatchOutput, "production batch outputs")
    safe_delete(ProductionBatchInput, "production batch inputs")
    safe_delete(ProductionBatch, "production batches")
    
    # Inventory
    print("  - Clearing inventory transactions and lots...")
    safe_delete(LotTransactionLog, "lot transaction logs")
    safe_delete(InventoryTransaction, "inventory transactions")
    safe_delete(Lot, "lots")
    
    # Logs
    print("  - Clearing logs...")
    safe_delete(LotDepletionLog, "lot depletion logs")
    safe_delete(ProductionLog, "production logs")
    safe_delete(PurchaseOrderLog, "purchase order logs")
    
    # Inventory data - use raw SQL for Items to bypass schema issues
    print("  - Clearing inventory data...")
    safe_delete(LotTransactionLog, "lot transaction logs")
    safe_delete(InventoryTransaction, "inventory transactions")
    safe_delete(Lot, "lots")
    safe_delete(ItemPackSize, "item pack sizes")
    # Try ORM first, then raw SQL if it fails
    try:
        count = Item.objects.all().count()
        if count > 0:
            Item.objects.all().delete()
            print(f"    Deleted {count} items")
        else:
            print(f"    No items to delete")
    except Exception:
        # Use raw SQL to delete items
        safe_delete_raw_sql("erp_core_item", "items")
    
    # Sales data
    print("  - Clearing sales data...")
    safe_delete(SalesCall, "sales calls")
    safe_delete(CustomerForecast, "customer forecasts")
    safe_delete(CustomerPricing, "customer pricing")
    safe_delete(CustomerContact, "customer contacts")
    safe_delete(ShipToLocation, "ship-to locations")
    safe_delete(Customer, "customers")
    
    # Quality data
    print("  - Clearing quality data...")
    safe_delete(SupplierDocument, "supplier documents")
    safe_delete(SupplierSurvey, "supplier surveys")
    safe_delete(VendorHistory, "vendor history")
    
    # Other master data
    print("  - Clearing other master data...")
    safe_delete(FormulaItem, "formula items")
    safe_delete(Formula, "formulas")
    safe_delete(CostMasterHistory, "cost master history")
    safe_delete(CostMaster, "cost master records")
    safe_delete(FinishedProductSpecification, "finished product specifications")
    safe_delete(VendorPricing, "vendor pricing")
    safe_delete(Vendor, "vendors")
    
    print("  [OK] Test data cleared (Chart of Accounts preserved)")

def reset_sequences():
    """Reset all number generation sequences to 0"""
    print("\nResetting number generation sequences...")
    
    with transaction.atomic():
        # Reset year-based sequences (for current year)
        today = timezone.now()
        year_prefix = today.strftime('%y')  # 2-digit year
        
        print(f"  - Resetting sequences for year {year_prefix}...")
        
        # Lot Number Sequence
        LotNumberSequence.objects.filter(year_prefix=year_prefix).update(sequence_number=0)
        print("    [OK] LotNumberSequence reset")
        
        # PO Number Sequence
        PONumberSequence.objects.filter(year_prefix=year_prefix).update(sequence_number=0)
        print("    [OK] PONumberSequence reset")
        
        # Sales Order Number Sequence
        SalesOrderNumberSequence.objects.filter(year_prefix=year_prefix).update(sequence_number=0)
        print("    [OK] SalesOrderNumberSequence reset")
        
        # Invoice Number Sequence
        InvoiceNumberSequence.objects.filter(year_prefix=year_prefix).update(sequence_number=0)
        print("    [OK] InvoiceNumberSequence reset")
        
        # Customer Number Sequence (single record)
        CustomerNumberSequence.objects.filter(id=1).update(sequence_number=0)
        # Create if doesn't exist
        CustomerNumberSequence.objects.get_or_create(
            id=1,
            defaults={'sequence_number': 0}
        )
        print("    [OK] CustomerNumberSequence reset")
        
        # Batch Number Sequence (for today)
        date_prefix = today.strftime('%Y%m%d')
        BatchNumberSequence.objects.filter(date_prefix=date_prefix).update(sequence_number=0)
        print(f"    [OK] BatchNumberSequence reset for {date_prefix}")
        
        print("  [OK] All sequences reset")

def main():
    print("=" * 60)
    print("CLEARING TEST DATA AND RESETTING NUMBER SEQUENCES")
    print("=" * 60)
    print()
    
    # Skip confirmation if running non-interactively
    if len(sys.argv) > 1 and sys.argv[1] == '--yes':
        print("Running in non-interactive mode...")
    else:
        # Confirm
        response = input("This will DELETE ALL test data and reset sequences. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return
    
    try:
        clear_test_data()
        reset_sequences()
        
        print("\n" + "=" * 60)
        print("[DONE] Test data cleared and sequences reset successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("  - Create new test data as needed")
        print("  - Number sequences will start from 0001/00001 for the current year")
        print("  - Batch numbers will start from 001 for today")
        
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
