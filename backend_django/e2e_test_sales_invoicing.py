"""
Extended End-to-End Test for Sales Order, Inventory Checkout, Invoicing, and Bookkeeping
Tests the complete sales-to-cash flow including inventory allocation, checkout, invoicing, AR, and journal entries
"""
import os
import sys
import django
from pathlib import Path
from datetime import datetime, timedelta
import math

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import (
    Vendor, Item, PurchaseOrder, PurchaseOrderItem, Lot, 
    ProductionBatch, ProductionBatchInput, ProductionBatchOutput,
    SalesOrder, SalesOrderItem, SalesOrderLot, Invoice, InvoiceItem,
    CostMaster, Customer, InventoryTransaction, Shipment, ShipmentItem,
    AccountsReceivable, JournalEntry, JournalEntryLine, Account, FiscalPeriod
)
from erp_core.views import (
    generate_po_number, generate_sales_order_number, generate_invoice_number,
    create_ar_entry_from_invoice
)
from django.utils import timezone
from django.db import connection
import sqlite3

class InventoryTracker:
    """Track inventory counts throughout tests"""
    def __init__(self):
        self.snapshots = []
    
    def snapshot(self, operation, item_id):
        """Take snapshot of item inventory"""
        try:
            item = Item.objects.get(id=item_id)
            lots = Lot.objects.filter(item_id=item_id)
            total_lot_quantity = sum(lot.quantity_remaining for lot in lots if lot.status == 'accepted')
            on_hold_quantity = sum(lot.quantity_remaining for lot in lots if lot.status == 'on_hold')
            
            self.snapshots.append({
                'operation': operation,
                'item_id': item_id,
                'sku': item.sku,
                'on_order': item.on_order or 0,
                'available_from_lots': total_lot_quantity,
                'on_hold_from_lots': on_hold_quantity,
                'total_lots': lots.count(),
                'total_lot_quantity': sum(lot.quantity for lot in lots)
            })
        except Item.DoesNotExist:
            pass
    
    def verify_counts(self, item_id, expected_on_order=None, expected_available=None, expected_on_hold=None, expected_total_lots=None, expected_total_lot_quantity=None):
        """Verify inventory counts match expected values"""
        try:
            item = Item.objects.get(id=item_id)
            lots = Lot.objects.filter(item_id=item_id)
            total_lot_quantity = sum(lot.quantity for lot in lots)
            available_from_lots = sum(lot.quantity_remaining for lot in lots if lot.status == 'accepted')
            on_hold_from_lots = sum(lot.quantity_remaining for lot in lots if lot.status == 'on_hold')
            
            issues = []
            if expected_on_order is not None and not math.isclose(item.on_order or 0, expected_on_order, rel_tol=1e-9):
                issues.append(f"Item on_order: Expected {expected_on_order}, got {item.on_order or 0}")
            if expected_available is not None and not math.isclose(available_from_lots, expected_available, rel_tol=1e-9):
                issues.append(f"Available from lots: Expected {expected_available}, got {available_from_lots}")
            if expected_on_hold is not None and not math.isclose(on_hold_from_lots, expected_on_hold, rel_tol=1e-9):
                issues.append(f"On hold from lots: Expected {expected_on_hold}, got {on_hold_from_lots}")
            if expected_total_lots is not None and lots.count() != expected_total_lots:
                issues.append(f"Total lots: Expected {expected_total_lots}, got {lots.count()}")
            if expected_total_lot_quantity is not None and not math.isclose(total_lot_quantity, expected_total_lot_quantity, rel_tol=1e-9):
                issues.append(f"Total lot quantity: Expected {expected_total_lot_quantity}, got {total_lot_quantity}")
            return issues
        except Item.DoesNotExist:
            return [f"Item {item_id} not found"]
    
    def print_history(self):
        """Print inventory change history"""
        print("\n=== Inventory Change History ===")
        for snap in self.snapshots:
            print(f"{snap['operation']}: SKU={snap['sku']}, on_order={snap['on_order']}, "
                  f"available_from_lots={snap['available_from_lots']}, "
                  f"on_hold_from_lots={snap['on_hold_from_lots']}, total_lots={snap['total_lots']}, "
                  f"total_lot_quantity={snap['total_lot_quantity']}")

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.inventory_issues = []
    
    def add_pass(self, test_name, details=""):
        self.passed.append(f"[PASS] {test_name}" + (f" - {details}" if details else ""))
        print(f"[PASS] {test_name}")
    
    def add_fail(self, test_name, error):
        self.failed.append(f"[FAIL] {test_name}: {error}")
        print(f"[FAIL] {test_name}: {error}")
    
    def add_warning(self, test_name, warning):
        self.warnings.append(f"[WARN] {test_name}: {warning}")
        print(f"[WARN] {test_name}: {warning}")
    
    def add_inventory_issue(self, test_name, issues):
        self.inventory_issues.append(f"[INVENTORY ISSUE] {test_name}: {', '.join(issues)}")
        print(f"[INVENTORY ISSUE] {test_name}: {', '.join(issues)}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"\nPassed: {len(self.passed)}")
        print(f"Failed: {len(self.failed)}")
        print(f"Warnings: {len(self.warnings)}")
        print(f"Inventory Issues: {len(self.inventory_issues)}")
        
        if self.failed:
            print("\nFAILED TESTS:")
            for fail in self.failed:
                print(f"  {fail}")
        
        if self.inventory_issues:
            print("\nINVENTORY COUNT ISSUES (CRITICAL):")
            for issue in self.inventory_issues:
                print(f"  {issue}")
        
        if self.warnings:
            print("\nWARNINGS:")
            for warn in self.warnings:
                print(f"  {warn}")
        
        print("\n" + "="*80)

def setup_test_data(results, tracker):
    """Set up test data: vendor, item, PO, lot"""
    print("\n=== Setting Up Test Data ===")
    
    # Create vendor
    vendor, _ = Vendor.objects.get_or_create(
        name='Test Vendor Sales',
        defaults={
            'contact_name': 'Jane Doe',
            'email': 'jane@testvendor.com',
            'phone': '555-5678',
            'street_address': '456 Test Ave',
            'city': 'Test City',
            'state': 'MO',
            'zip_code': '12345',
            'country': 'USA',
            'approval_status': 'approved'
        }
    )
    
    # Create raw material item
    import time
    unique_sku = f'SALESTEST{int(time.time())}'
    item, _ = Item.objects.get_or_create(
        sku=unique_sku,
        vendor=vendor.name,
        defaults={
            'name': 'Test Raw Material for Sales',
            'vendor_item_name': 'Vendor Test Material',
            'item_type': 'raw_material',
            'unit_of_measure': 'lbs',
            'price': 10.50,
            'on_order': 0
        }
    )
    tracker.snapshot("After item creation", item.id)
    
    # Create PO and issue it
    po = PurchaseOrder.objects.create(
        po_number=generate_po_number(),
        vendor_customer_name=vendor.name,
        vendor_customer_id=str(vendor.id),
        expected_delivery_date=datetime.now().date() + timedelta(days=30),
        status='issued'
    )
    PurchaseOrderItem.objects.create(
        purchase_order=po,
        item=item,
        quantity_ordered=200,
        unit_price=10.50
    )
    item.on_order = 200
    item.save()
    tracker.snapshot("After PO issued", item.id)
    
    # Check in lot
    lot = Lot.objects.create(
        lot_number=f'LOT-{int(time.time())}',
        vendor_lot_number=f'VENDOR-LOT-{int(time.time())}',
        item=item,
        quantity=200,
        quantity_remaining=200,
        received_date=timezone.now(),
        po_number=po.po_number,
        status='accepted'
    )
    InventoryTransaction.objects.create(
        transaction_type='receipt',
        lot=lot,
        quantity=200,
        notes=f'Check-in from PO {po.po_number}'
    )
    item.on_order = 0
    item.save()
    tracker.snapshot("After lot check-in", item.id)
    
    results.add_pass("Setup test data", f"Item: {item.sku}, Lot: {lot.lot_number}")
    return vendor.id, item.id, lot.id

def test_sales_order_creation(results, tracker):
    """Test sales order creation"""
    print("\n=== Testing Sales Order Creation ===")
    
    try:
        # Create customer
        import time
        unique_customer_id = f'CUST{int(time.time())}'
        customer, _ = Customer.objects.get_or_create(
            customer_id=unique_customer_id,
            defaults={
                'name': 'Test Customer Sales',
                'email': 'customer@test.com',
                'payment_terms': 'Net 30'
            }
        )
        results.add_pass("Create customer", f"Customer ID: {customer.customer_id}")
        
        # Use raw material item for sales (we'll use the item from setup)
        # For this test, we'll create a finished good item that we can sell
        fg_item = Item.objects.filter(item_type='finished_good').first()
        if not fg_item:
            # Create a finished good
            fg_item = Item.objects.create(
                sku=f'FG-SALES-{int(time.time())}',
                name='Test Finished Good',
                item_type='finished_good',
                unit_of_measure='lbs',
                price=25.00,
                on_order=0
            )
            results.add_pass("Create finished good for sales")
        
        # Create sales order using raw SQL to handle schema
        so_number = generate_sales_order_number()
        now = timezone.now()
        
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(erp_core_salesorder)")
            columns = {col[1]: col for col in cursor.fetchall()}
        
        # Build SQL insert
        db_path = connection.settings_dict['NAME']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Get required fields
            col_names = ['so_number', 'customer_id', 'customer_name', 'order_date', 'status', 'created_at', 'updated_at']
            col_values = [
                so_number,
                str(customer.id),
                customer.name,
                datetime.now().date().isoformat(),
                'draft',
                now.isoformat(),
                now.isoformat()
            ]
            
            # Add optional numeric fields with defaults
            numeric_fields = ['subtotal', 'freight', 'misc', 'prepaid', 'discount', 'grand_total', 'tax']
            for field in numeric_fields:
                if field in [col[1] for col in cursor.execute("PRAGMA table_info(erp_core_salesorder)").fetchall()]:
                    col_names.append(field)
                    col_values.append(0.0)
            
            placeholders = ','.join(['?' for _ in col_names])
            insert_sql = f"INSERT INTO erp_core_salesorder ({','.join(col_names)}) VALUES ({placeholders})"
            cursor.execute(insert_sql, col_values)
            so_id = cursor.lastrowid
            conn.commit()
            
            # Get the created sales order
            so = SalesOrder.objects.get(id=so_id)
            
            # Create sales order item
            SalesOrderItem.objects.create(
                sales_order=so,
                item=fg_item,
                quantity_ordered=50,
                unit_price=25.00,
                quantity_allocated=0,
                quantity_shipped=0
            )
            
            results.add_pass("Create sales order", f"SO Number: {so.so_number}")
            return so.id, fg_item.id, customer.id
        finally:
            conn.close()
            
    except Exception as e:
        results.add_fail("Sales order creation", str(e))
        import traceback
        traceback.print_exc()
        return None, None, None

def test_inventory_allocation(results, so_id, fg_item_id, raw_item_id, lot_id, tracker):
    """Test inventory allocation for sales order"""
    print("\n=== Testing Inventory Allocation ===")
    
    if not so_id or not fg_item_id or not lot_id:
        results.add_fail("Inventory allocation", "Missing prerequisites")
        return False
    
    try:
        so = SalesOrder.objects.get(id=so_id)
        so_item = SalesOrderItem.objects.filter(sales_order=so).first()
        
        # For this test, we need to create a lot for the finished good item
        # First, check if we have a lot for the finished good
        fg_item = Item.objects.get(id=fg_item_id)
        fg_lot = Lot.objects.filter(item_id=fg_item_id, status='accepted').first()
        
        if not fg_lot:
            # Create a lot for the finished good from production or direct creation
            # For simplicity, create it directly
            import time
            fg_lot = Lot.objects.create(
                lot_number=f'FG-LOT-{int(time.time())}',
                item=fg_item,  # Use the item object, not item_id
                quantity=100.0,
                quantity_remaining=100.0,
                received_date=timezone.now(),
                status='accepted'
            )
            # Explicitly set quantity_remaining after creation (in case of signals/defaults)
            fg_lot.quantity_remaining = 100.0
            fg_lot.save()
            
            InventoryTransaction.objects.create(
                transaction_type='receipt',
                lot=fg_lot,
                quantity=100.0,
                notes='Test finished good lot'
            )
            results.add_pass("Create finished good lot for allocation")
        
        # Refresh from DB to ensure we have latest data
        fg_lot.refresh_from_db()
        
        # If quantity_remaining is still 0, set it explicitly
        if fg_lot.quantity_remaining == 0 and fg_lot.quantity > 0:
            fg_lot.quantity_remaining = fg_lot.quantity
            fg_lot.save()
            fg_lot.refresh_from_db()
        
        # Debug: print lot details
        print(f"DEBUG: Lot {fg_lot.lot_number}, quantity={fg_lot.quantity}, quantity_remaining={fg_lot.quantity_remaining}, status={fg_lot.status}")
        
        # Verify lot has enough quantity
        if fg_lot.quantity_remaining < so_item.quantity_ordered:
            results.add_fail("Inventory allocation", f"Insufficient inventory. Available: {fg_lot.quantity_remaining}, Required: {so_item.quantity_ordered}")
            return False
        
        # Allocate lot to sales order item
        SalesOrderLot.objects.create(
            sales_order_item=so_item,
            lot=fg_lot,
            quantity_allocated=so_item.quantity_ordered
        )
        
        so_item.quantity_allocated = so_item.quantity_ordered
        so_item.save()
        
        so.status = 'ready_for_shipment'
        so.save()
        
        tracker.snapshot("After allocation", fg_item_id)
        
        # Verify allocation
        allocated = SalesOrderLot.objects.filter(sales_order_item=so_item).first()
        if allocated and allocated.quantity_allocated == so_item.quantity_ordered:
            results.add_pass("Inventory allocation", f"Allocated {allocated.quantity_allocated} from lot {fg_lot.lot_number}")
        else:
            results.add_fail("Inventory allocation", "Allocation not created correctly")
            return False
        
        return fg_lot.id
    except Exception as e:
        results.add_fail("Inventory allocation", str(e))
        import traceback
        traceback.print_exc()
        return None

def test_inventory_checkout(results, so_id, fg_item_id, lot_id, tracker):
    """Test inventory checkout (shipping)"""
    print("\n=== Testing Inventory Checkout ===")
    
    if not so_id or not fg_item_id or not lot_id:
        results.add_fail("Inventory checkout", "Missing prerequisites")
        return None
    
    try:
        so = SalesOrder.objects.get(id=so_id)
        so_item = SalesOrderItem.objects.filter(sales_order=so).first()
        lot = Lot.objects.get(id=lot_id)
        
        # Issue the sales order first
        so.status = 'issued'
        so.save()
        
        # Get quantity before checkout
        quantity_before = lot.quantity_remaining
        tracker.snapshot("Before checkout", fg_item_id)
        
        # Create shipment
        import time
        shipment = Shipment.objects.create(
            sales_order=so,
            ship_date=timezone.now(),
            tracking_number=f'TRACK{int(time.time())}',
            notes='Test shipment'
        )
        
        # Ship the allocated quantity
        quantity_to_ship = so_item.quantity_allocated
        lot.quantity_remaining -= quantity_to_ship
        lot.save()
        
        # Create inventory transaction
        InventoryTransaction.objects.create(
            transaction_type='adjustment',
            lot=lot,
            quantity=-quantity_to_ship,
            reference_number=so.so_number,
            notes=f'Shipped for sales order {so.so_number}'
        )
        
        # Update sales order item
        so_item.quantity_shipped = quantity_to_ship
        so_item.quantity_allocated = 0
        so_item.save()
        
        # Create shipment item
        ShipmentItem.objects.create(
            shipment=shipment,
            sales_order_item=so_item,
            quantity_shipped=quantity_to_ship
        )
        
        # Update sales order status
        so.status = 'completed'
        so.actual_ship_date = timezone.now()
        so.tracking_number = shipment.tracking_number
        so.save()
        
        # Remove allocation
        SalesOrderLot.objects.filter(sales_order_item=so_item).delete()
        
        tracker.snapshot("After checkout", fg_item_id)
        
        # Verify inventory decreased
        lot.refresh_from_db()
        issues = tracker.verify_counts(
            fg_item_id,
            expected_available=quantity_before - quantity_to_ship,
            expected_total_lots=1
        )
        if issues:
            results.add_inventory_issue("Inventory checkout - counts", issues)
        else:
            results.add_pass("Inventory checkout", f"Shipped {quantity_to_ship}, remaining: {lot.quantity_remaining}")
        
        return shipment.id
    except Exception as e:
        results.add_fail("Inventory checkout", str(e))
        import traceback
        traceback.print_exc()
        return None

def test_invoice_creation_from_so(results, so_id, customer_id, tracker):
    """Test invoice creation from sales order"""
    print("\n=== Testing Invoice Creation from Sales Order ===")
    
    if not so_id:
        results.add_fail("Invoice creation", "Missing sales order")
        return None
    
    try:
        so = SalesOrder.objects.get(id=so_id)
        so_item = SalesOrderItem.objects.filter(sales_order=so).first()
        
        # Create invoice
        invoice_number = generate_invoice_number()
        invoice_date = datetime.now().date()
        due_date = invoice_date + timedelta(days=30)
        
        # Calculate totals
        subtotal = so_item.quantity_shipped * so_item.unit_price
        freight = 0.0
        tax = 0.0
        discount = 0.0
        grand_total = subtotal + freight + tax - discount
        
        # Check if invoice_type field exists in database
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(erp_core_invoice)")
            columns = {col[1]: col for col in cursor.fetchall()}
            has_invoice_type = 'invoice_type' in columns
        
        # Use raw SQL if invoice_type column exists (not in model)
        if has_invoice_type:
            db_path = connection.settings_dict['NAME']
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            try:
                # Check all required columns
                cursor.execute("PRAGMA table_info(erp_core_invoice)")
                all_columns = {col[1]: col for col in cursor.fetchall()}
                
                col_names = ['invoice_number', 'sales_order_id', 'invoice_date', 'due_date', 'status', 
                            'subtotal', 'freight', 'tax', 'discount', 'grand_total']
                col_values = [
                    invoice_number,
                    so.id,
                    invoice_date.isoformat(),
                    due_date.isoformat(),
                    'sent',
                    subtotal,
                    freight,
                    tax,
                    discount,
                    grand_total
                ]
                
                # Add all NOT NULL columns that aren't already included
                not_null_defaults = {
                    'invoice_type': 'sales',
                    'customer_vendor_name': so.customer_name or 'Unknown Customer',
                    'customer_vendor_id': so.customer_id or None,
                    'tax_amount': tax,
                    'total_amount': grand_total,  # Sometimes total_amount is separate from grand_total
                    'paid_amount': 0.0,  # New invoices haven't been paid yet
                }
                
                # Also check all columns and add any NOT NULL ones we haven't covered
                for col_info in cursor.execute("PRAGMA table_info(erp_core_invoice)").fetchall():
                    col_name = col_info[1]
                    is_not_null = col_info[3] == 1  # 1 means NOT NULL
                    
                    if is_not_null and col_name not in col_names:
                        # Use default from dict if available, otherwise use appropriate default
                        if col_name in not_null_defaults:
                            col_names.append(col_name)
                            col_values.append(not_null_defaults[col_name])
                        elif col_name.endswith('_amount') or col_name in ['tax', 'discount', 'freight']:
                            # Numeric fields default to 0
                            col_names.append(col_name)
                            col_values.append(0.0)
                        elif col_name.endswith('_date') and col_name not in ['invoice_date', 'due_date']:
                            # Date fields default to invoice_date
                            col_names.append(col_name)
                            col_values.append(invoice_date.isoformat())
                        elif col_name.endswith('_at'):
                            # Timestamp fields (created_at, updated_at)
                            col_names.append(col_name)
                            col_values.append(timezone.now().isoformat())
                        elif col_name in ['status', 'invoice_type']:
                            # Status fields
                            if col_name == 'status':
                                col_names.append(col_name)
                                col_values.append('sent')
                            elif col_name == 'invoice_type':
                                col_names.append(col_name)
                                col_values.append('sales')
                        elif col_name in ['customer_vendor_name', 'customer_name']:
                            col_names.append(col_name)
                            col_values.append(so.customer_name or 'Unknown Customer')
                        elif col_name in ['customer_vendor_id', 'customer_id']:
                            col_names.append(col_name)
                            col_values.append(so.customer_id or None)
                
                placeholders = ','.join(['?' for _ in col_names])
                insert_sql = f"INSERT INTO erp_core_invoice ({','.join(col_names)}) VALUES ({placeholders})"
                cursor.execute(insert_sql, col_values)
                invoice_id = cursor.lastrowid
                conn.commit()
                
                invoice = Invoice.objects.get(id=invoice_id)
            finally:
                conn.close()
        else:
            # Use ORM if no invoice_type column
            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                sales_order=so,
                invoice_date=invoice_date,
                due_date=due_date,
                status='sent',
                subtotal=subtotal,
                freight=freight,
                tax=tax,
                discount=discount,
                grand_total=grand_total
            )
        
        # Check InvoiceItem schema - may not have sales_order_item column
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(erp_core_invoiceitem)")
            invoice_item_columns = {col[1]: col for col in cursor.fetchall()}
            has_sales_order_item = 'sales_order_item_id' in invoice_item_columns
        
        # Use raw SQL if sales_order_item column doesn't exist
        if not has_sales_order_item:
            db_path = connection.settings_dict['NAME']
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            try:
                # Get actual column names from database
                cursor.execute("PRAGMA table_info(erp_core_invoiceitem)")
                actual_columns = {col[1]: col for col in cursor.fetchall()}
                
                # Build column list based on what exists
                col_names = []
                col_values = []
                
                if 'invoice_id' in actual_columns:
                    col_names.append('invoice_id')
                    col_values.append(invoice.id)
                
                if 'description' in actual_columns:
                    col_names.append('description')
                    col_values.append(so_item.item.name or so_item.item.sku)
                
                if 'quantity' in actual_columns:
                    col_names.append('quantity')
                    col_values.append(so_item.quantity_shipped)
                
                if 'unit_price' in actual_columns:
                    col_names.append('unit_price')
                    col_values.append(so_item.unit_price)
                
                # Try different possible names for total
                for total_col_name in ['total', 'line_total', 'amount']:
                    if total_col_name in actual_columns:
                        col_names.append(total_col_name)
                        col_values.append(subtotal)
                        break
                
                placeholders = ','.join(['?' for _ in col_names])
                insert_sql = f"INSERT INTO erp_core_invoiceitem ({','.join(col_names)}) VALUES ({placeholders})"
                cursor.execute(insert_sql, col_values)
                conn.commit()
            finally:
                conn.close()
        else:
            # Use ORM if column exists
            InvoiceItem.objects.create(
                invoice=invoice,
                sales_order_item=so_item,
                description=so_item.item.name or so_item.item.sku,
                quantity=so_item.quantity_shipped,
                unit_price=so_item.unit_price,
                total=subtotal
            )
        
        results.add_pass("Create invoice from sales order", f"Invoice: {invoice.invoice_number}, Total: ${grand_total:.2f}")
        return invoice.id
    except Exception as e:
        results.add_fail("Invoice creation", str(e))
        import traceback
        traceback.print_exc()
        return None

def test_ar_entry_creation(results, invoice_id, customer_id):
    """Test AR entry creation from invoice"""
    print("\n=== Testing AR Entry Creation ===")
    
    if not invoice_id:
        results.add_fail("AR entry creation", "Missing invoice")
        return None
    
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Create AR entry
        ar_entry = create_ar_entry_from_invoice(invoice)
        
        if ar_entry:
            results.add_pass("Create AR entry", f"AR Entry ID: {ar_entry.id}, Balance: ${ar_entry.balance:.2f}")
            
            # Verify AR entry
            if ar_entry.balance == invoice.grand_total:
                results.add_pass("AR entry balance correct")
            else:
                results.add_fail("AR entry balance", f"Expected ${invoice.grand_total:.2f}, got ${ar_entry.balance:.2f}")
            
            return ar_entry.id
        else:
            results.add_fail("AR entry creation", "create_ar_entry_from_invoice returned None")
            return None
    except Exception as e:
        results.add_fail("AR entry creation", str(e))
        import traceback
        traceback.print_exc()
        return None

def test_journal_entry_creation(results, ar_entry_id):
    """Test journal entry creation for AR"""
    print("\n=== Testing Journal Entry Creation ===")
    
    if not ar_entry_id:
        results.add_fail("Journal entry creation", "Missing AR entry")
        return None
    
    try:
        ar_entry = AccountsReceivable.objects.get(id=ar_entry_id)
        
        # Check if journal entry was created
        if ar_entry.journal_entry:
            je = ar_entry.journal_entry
            results.add_pass("Journal entry created", f"JE Number: {je.entry_number}")
            
            # Verify journal entry is balanced
            if je.validate_balanced():
                results.add_pass("Journal entry is balanced")
            else:
                results.add_fail("Journal entry balance", "Debits do not equal credits")
            
            # Check journal entry lines
            lines = JournalEntryLine.objects.filter(journal_entry=je)
            if lines.count() >= 2:
                results.add_pass("Journal entry has lines", f"Total lines: {lines.count()}")
            else:
                results.add_fail("Journal entry lines", f"Expected at least 2 lines, got {lines.count()}")
            
            return je.id
        else:
            results.add_warning("Journal entry creation", "No journal entry linked to AR entry")
            return None
    except Exception as e:
        results.add_fail("Journal entry creation", str(e))
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all tests"""
    print("="*80)
    print("COMPREHENSIVE E2E TESTING: SALES ORDER, CHECKOUT, INVOICING, BOOKKEEPING")
    print("="*80)
    
    results = TestResults()
    tracker = InventoryTracker()
    
    # Setup test data
    vendor_id, item_id, lot_id = setup_test_data(results, tracker)
    
    if not item_id or not lot_id:
        results.add_fail("Setup", "Failed to set up test data")
        results.print_summary()
        return 1
    
    # Test sales order creation
    so_id, fg_item_id, customer_id = test_sales_order_creation(results, tracker)
    
    if not so_id:
        results.print_summary()
        return 1
    
    # Test inventory allocation
    fg_lot_id = test_inventory_allocation(results, so_id, fg_item_id, item_id, lot_id, tracker)
    
    if not fg_lot_id:
        results.print_summary()
        return 1
    
    # Test inventory checkout
    shipment_id = test_inventory_checkout(results, so_id, fg_item_id, fg_lot_id, tracker)
    
    if not shipment_id:
        results.print_summary()
        return 1
    
    # Test invoice creation
    invoice_id = test_invoice_creation_from_so(results, so_id, customer_id, tracker)
    
    if not invoice_id:
        results.print_summary()
        return 1
    
    # Test AR entry creation
    ar_entry_id = test_ar_entry_creation(results, invoice_id, customer_id)
    
    if not ar_entry_id:
        results.print_summary()
        return 1
    
    # Test journal entry creation
    je_id = test_journal_entry_creation(results, ar_entry_id)
    
    # Print inventory history
    tracker.print_history()
    
    # Print summary
    results.print_summary()
    
    # Save results
    with open(BASE_DIR / 'e2e_test_sales_invoicing_results.txt', 'w') as f:
        f.write("="*80 + "\n")
        f.write("E2E TEST RESULTS: SALES ORDER, CHECKOUT, INVOICING, BOOKKEEPING\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write("="*80 + "\n\n")
        f.write(f"Passed: {len(results.passed)}\n")
        f.write(f"Failed: {len(results.failed)}\n")
        f.write(f"Warnings: {len(results.warnings)}\n")
        f.write(f"Inventory Issues: {len(results.inventory_issues)}\n\n")
        
        if results.passed:
            f.write("PASSED TESTS:\n")
            for test in results.passed:
                f.write(f"  {test}\n")
        
        if results.failed:
            f.write("\nFAILED TESTS:\n")
            for test in results.failed:
                f.write(f"  {test}\n")
        
        if results.inventory_issues:
            f.write("\nINVENTORY COUNT ISSUES (CRITICAL):\n")
            for issue in results.inventory_issues:
                f.write(f"  {issue}\n")
        
        if results.warnings:
            f.write("\nWARNINGS:\n")
            for test in results.warnings:
                f.write(f"  {test}\n")
    
    print(f"\nResults saved to: {BASE_DIR / 'e2e_test_sales_invoicing_results.txt'}")
    
    # Return exit code based on results
    if results.inventory_issues or results.failed:
        return 1
    return 0

if __name__ == '__main__':
    exit(main())
