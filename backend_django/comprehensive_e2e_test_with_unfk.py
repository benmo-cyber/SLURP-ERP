"""
Comprehensive End-to-End Testing with UNFK and Inventory Count Verification
Tests all major flows and ensures inventory counts remain correct
"""
import os
import sys
import django
from pathlib import Path
import requests
import json
from datetime import datetime, timedelta

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import (
    Vendor, Item, PurchaseOrder, PurchaseOrderItem, Lot, 
    ProductionBatch, SalesOrder, SalesOrderItem, Invoice, InvoiceItem,
    CostMaster, Customer, InventoryTransaction
)

API_BASE_URL = 'http://localhost:8000/api'

class InventoryTracker:
    """Track inventory counts throughout tests"""
    def __init__(self):
        self.snapshots = []
    
    def snapshot(self, operation, item_id):
        """Take snapshot of item inventory"""
        try:
            item = Item.objects.get(id=item_id)
            # Calculate available from lots
            lots = Lot.objects.filter(item_id=item_id)
            total_lot_quantity = sum(lot.quantity_remaining for lot in lots if lot.status != 'on_hold')
            on_hold_quantity = sum(lot.quantity_remaining for lot in lots if lot.status == 'on_hold')
            
            self.snapshots.append({
                'operation': operation,
                'item_id': item_id,
                'sku': item.sku,
                'on_order': item.on_order or 0,
                'available_from_lots': total_lot_quantity,
                'on_hold_from_lots': on_hold_quantity,
                'total_lots': lots.count()
            })
        except Item.DoesNotExist:
            pass
    
    def verify_counts(self, item_id, expected_on_order=None, expected_lot_count=None):
        """Verify inventory counts match expected values"""
        try:
            item = Item.objects.get(id=item_id)
            issues = []
            
            if expected_on_order is not None and item.on_order != expected_on_order:
                issues.append(f"on_order: expected {expected_on_order}, got {item.on_order}")
            
            if expected_lot_count is not None:
                lot_count = Lot.objects.filter(item_id=item_id).count()
                if lot_count != expected_lot_count:
                    issues.append(f"lot_count: expected {expected_lot_count}, got {lot_count}")
            
            return issues
        except Item.DoesNotExist:
            return [f"Item {item_id} not found"]
    
    def print_history(self):
        """Print inventory change history"""
        print("\n=== Inventory Change History ===")
        for snap in self.snapshots:
            print(f"{snap['operation']}: SKU={snap['sku']}, on_order={snap['on_order']}, "
                  f"available_from_lots={snap['available_from_lots']}, "
                  f"on_hold_from_lots={snap['on_hold_from_lots']}, total_lots={snap['total_lots']}")

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

def make_api_request(method, endpoint, data=None, files=None):
    """Make API request and return response"""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        if method == 'GET':
            response = requests.get(url)
        elif method == 'POST':
            if files:
                response = requests.post(url, data=data, files=files)
            else:
                response = requests.post(url, json=data)
        elif method == 'PUT':
            response = requests.put(url, json=data)
        elif method == 'DELETE':
            response = requests.delete(url)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return response
    except Exception as e:
        return None

def test_vendor_creation(results):
    """Test creating vendors"""
    print("\n=== Testing Vendor Creation ===")
    
    vendor_data = {
        'name': 'Test Vendor Inc',
        'contact_name': 'John Doe',
        'email': 'john@testvendor.com',
        'phone': '555-1234',
        'street_address': '123 Test St',
        'city': 'Test City',
        'state': 'MO',
        'zip_code': '12345',
        'country': 'USA',
        'approval_status': 'approved'
    }
    
    response = make_api_request('POST', '/vendors/', vendor_data)
    if response and response.status_code == 201:
        vendor_id = response.json().get('id')
        results.add_pass("Create vendor", f"Vendor ID: {vendor_id}")
        return vendor_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create vendor", error)
        return None

def test_item_creation(results, vendor_id, tracker):
    """Test creating items"""
    print("\n=== Testing Item Creation ===")
    
    if not vendor_id:
        results.add_fail("Create item", "No vendor available")
        return None
    
    # Test 1: Create item
    item_data = {
        'sku': 'TEST001',
        'name': 'Test Item 1',
        'vendor': 'Test Vendor Inc',
        'vendor_item_name': 'Vendor Test Item',
        'item_type': 'raw_material',
        'unit_of_measure': 'lbs',
        'price': 10.50,
        'hts_code': '12345678',
        'country_of_origin': 'USA'
    }
    
    response = make_api_request('POST', '/items/', item_data)
    if response and response.status_code == 201:
        item_id = response.json().get('id')
        results.add_pass("Create item", f"Item ID: {item_id}")
        tracker.snapshot("After item creation", item_id)
        
        # Test 2: Try duplicate SKU (should fail)
        dup_response = make_api_request('POST', '/items/', item_data)
        if dup_response and dup_response.status_code == 400:
            results.add_pass("Reject duplicate SKU")
        else:
            results.add_fail("Reject duplicate SKU", "Should return 400")
        
        return item_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create item", error)
        return None

def test_purchase_order_flow(results, vendor_id, item_id, tracker):
    """Test purchase order creation and issuing"""
    print("\n=== Testing Purchase Order Flow ===")
    
    if not vendor_id or not item_id:
        results.add_fail("Purchase order flow", "Missing prerequisites")
        return None
    
    # Get initial inventory
    tracker.snapshot("Before PO creation", item_id)
    initial_available = Item.objects.get(id=item_id).available or 0
    
    # Create PO
    po_data = {
        'vendor_id': vendor_id,
        'expected_delivery_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
        'items': [
            {
                'item_id': item_id,
                'quantity': 100,
                'unit_cost': 10.50
            }
        ]
    }
    
    response = make_api_request('POST', '/purchase-orders/', po_data)
    if response and response.status_code == 201:
        po_data_resp = response.json()
        po_number = po_data_resp.get('po_number')
        po_id = po_data_resp.get('id')
        results.add_pass("Create purchase order", f"PO Number: {po_number}")
        tracker.snapshot("After PO creation", item_id)
        
        # Issue PO
        issue_response = make_api_request('POST', f'/purchase-orders/{po_id}/issue/')
        if issue_response and issue_response.status_code == 200:
            results.add_pass("Issue purchase order")
            tracker.snapshot("After PO issued", item_id)
            
            # Verify on_order increased
            issues = tracker.verify_counts(item_id, expected_on_order=100)
            if issues:
                results.add_inventory_issue("PO issued - on_order", issues)
            else:
                results.add_pass("PO issued - on_order updated correctly")
            
            return po_id
        else:
            error = issue_response.json() if issue_response else "No response"
            results.add_fail("Issue purchase order", error)
            return None
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create purchase order", error)
        return None

def test_lot_check_in(results, po_id, item_id, tracker):
    """Test lot check-in and verify inventory"""
    print("\n=== Testing Lot Check-In ===")
    
    if not po_id or not item_id:
        results.add_fail("Lot check-in", "Missing prerequisites")
        return None
    
    po = PurchaseOrder.objects.get(id=po_id)
    
    # Check in lot
    lot_data = {
        'item_id': item_id,
        'vendor_lot_number': 'VENDOR-LOT-001',
        'quantity': 100,
        'received_date': datetime.now().isoformat(),
        'po_number': po.po_number,
        'tracking_number': 'TRACK123456',
        'status': 'accepted'
    }
    
    response = make_api_request('POST', '/lots/', lot_data)
    if response and response.status_code == 201:
        lot_id = response.json().get('id')
        results.add_pass("Check in lot", f"Lot ID: {lot_id}")
        tracker.snapshot("After lot check-in", item_id)
        
        # Verify on_order decreased and lot created
        issues = tracker.verify_counts(item_id, expected_on_order=0, expected_lot_count=1)
        if issues:
            results.add_inventory_issue("Lot check-in - inventory counts", issues)
        else:
            # Verify lot quantity
            lot = Lot.objects.get(id=lot_id)
            if lot.quantity == 100:
                results.add_pass("Lot check-in - inventory counts correct")
            else:
                results.add_inventory_issue("Lot check-in - lot quantity", 
                                          [f"Expected lot quantity 100, got {lot.quantity}"])
        
        return lot_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Check in lot", error)
        return None

def test_unfk_reverse_check_in(results, lot_id, item_id, tracker):
    """Test UNFK (reverse check-in) and verify inventory"""
    print("\n=== Testing UNFK - Reverse Check-In ===")
    
    if not lot_id or not item_id:
        results.add_fail("UNFK reverse check-in", "Missing prerequisites")
        return None
    
    # Get inventory before UNFK
    tracker.snapshot("Before UNFK reverse check-in", item_id)
    before_available = Item.objects.get(id=item_id).available or 0
    
    # Reverse check-in
    response = make_api_request('POST', f'/lots/{lot_id}/reverse-check-in/')
    if response and response.status_code == 200:
        results.add_pass("UNFK reverse check-in")
        tracker.snapshot("After UNFK reverse check-in", item_id)
        
        # Verify lot was deleted
        lot_exists = Lot.objects.filter(id=lot_id).exists()
        if not lot_exists:
            results.add_pass("UNFK reverse check-in - lot deleted")
        else:
            results.add_inventory_issue("UNFK reverse check-in - lot", 
                                      ["Lot should be deleted but still exists"])
        
        return True
    else:
        error = response.json() if response else "No response"
        results.add_fail("UNFK reverse check-in", error)
        return False

def test_production_batch_flow(results, item_id, tracker):
    """Test production batch creation and closing"""
    print("\n=== Testing Production Batch Flow ===")
    
    # Create finished good
    fg_item_data = {
        'sku': 'FG001',
        'name': 'Finished Good 1',
        'item_type': 'finished_good',
        'unit_of_measure': 'lbs',
        'price': 25.00
    }
    
    response = make_api_request('POST', '/items/', fg_item_data)
    if response and response.status_code == 201:
        fg_item_id = response.json().get('id')
        results.add_pass("Create finished good item")
        tracker.snapshot("After FG creation", fg_item_id)
        
        # Create production batch
        batch_data = {
            'finished_good_item': fg_item_id,
            'quantity_produced': 50,
            'production_date': datetime.now().strftime('%Y-%m-%d'),
            'batch_type': 'production',
            'inputs': [
                {
                    'item_id': item_id,
                    'quantity': 40,
                    'lot_id': None  # Will use available lots
                }
            ]
        }
        
        response = make_api_request('POST', '/production-batches/', batch_data)
        if response and response.status_code == 201:
            batch_id = response.json().get('id')
            batch_number = response.json().get('batch_number')
            results.add_pass("Create production batch", f"Batch: {batch_number}")
            tracker.snapshot("After batch creation", item_id)
            tracker.snapshot("After batch creation", fg_item_id)
            
            # Close batch
            close_response = make_api_request('POST', f'/production-batches/{batch_id}/close/')
            if close_response and close_response.status_code == 200:
                results.add_pass("Close production batch")
                tracker.snapshot("After batch closed", item_id)
                tracker.snapshot("After batch closed", fg_item_id)
                
                # Verify output lot created
                lot = Lot.objects.filter(batch_number=batch_number).first()
                if lot:
                    results.add_pass("Output lot created when batch closed")
                else:
                    results.add_fail("Output lot created when batch closed", "Lot not found")
                
                return batch_id
            else:
                error = close_response.json() if close_response else "No response"
                results.add_fail("Close production batch", error)
                return None
        else:
            error = response.json() if response else "No response"
            results.add_fail("Create production batch", error)
            return None
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create finished good item", error)
        return None

def test_unfk_batch(results, batch_id, item_id, fg_item_id, tracker):
    """Test UNFK batch and verify inventory"""
    print("\n=== Testing UNFK - Production Batch ===")
    
    if not batch_id:
        results.add_fail("UNFK batch", "No batch available")
        return False
    
    # Get inventory before UNFK
    tracker.snapshot("Before UNFK batch", item_id)
    tracker.snapshot("Before UNFK batch", fg_item_id)
    before_input_available = Item.objects.get(id=item_id).available or 0
    before_output_available = Item.objects.get(id=fg_item_id).available or 0
    
    # Reverse batch
    response = make_api_request('POST', f'/production-batches/{batch_id}/reverse/')
    if response and response.status_code == 200:
        results.add_pass("UNFK batch")
        tracker.snapshot("After UNFK batch", item_id)
        tracker.snapshot("After UNFK batch", fg_item_id)
        
        # Verify batch was deleted and output lot removed
        batch_exists = ProductionBatch.objects.filter(id=batch_id).exists()
        if not batch_exists:
            results.add_pass("UNFK batch - batch deleted")
        else:
            results.add_inventory_issue("UNFK batch - batch", ["Batch should be deleted but still exists"])
        
        # Verify output lot was deleted
        output_lots = Lot.objects.filter(batch_number__startswith='BT')
        if output_lots.count() == 0:
            results.add_pass("UNFK batch - output lot removed")
        else:
            results.add_inventory_issue("UNFK batch - output lot", 
                                      [f"Output lot should be deleted but {output_lots.count()} still exist"])
        
        return True
    else:
        error = response.json() if response else "No response"
        results.add_fail("UNFK batch", error)
        return False

def test_invoice_creation(results):
    """Test invoice creation"""
    print("\n=== Testing Invoice Creation ===")
    
    # Create customer
    customer_data = {
        'name': 'Test Customer',
        'email': 'customer@test.com',
        'payment_terms': 'Net 30'
    }
    
    response = make_api_request('POST', '/customers/', customer_data)
    if response and response.status_code == 201:
        customer_id = response.json().get('id')
        results.add_pass("Create customer")
        
        # Get a finished good item
        fg_item = Item.objects.filter(item_type='finished_good').first()
        if not fg_item:
            results.add_warning("Create invoice", "No finished good items available")
            return None
        
        # Create sales order
        so_data = {
            'customer_id': customer_id,
            'order_date': datetime.now().strftime('%Y-%m-%d'),
            'expected_ship_date': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            'items': [
                {
                    'item_id': fg_item.id,
                    'quantity_ordered': 25,
                    'unit_price': 25.00
                }
            ]
        }
        
        response = make_api_request('POST', '/sales-orders/', so_data)
        if response and response.status_code == 201:
            so_id = response.json().get('id')
            results.add_pass("Create sales order")
            
            # Create invoice
            invoice_data = {
                'sales_order_id': so_id,
                'invoice_date': datetime.now().strftime('%Y-%m-%d'),
                'due_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            }
            
            response = make_api_request('POST', '/invoices/', invoice_data)
            if response and response.status_code == 201:
                invoice_id = response.json().get('id')
                invoice_number = response.json().get('invoice_number')
                results.add_pass("Create invoice", f"Invoice Number: {invoice_number}")
                return invoice_id
            else:
                error = response.json() if response else "No response"
                results.add_fail("Create invoice", error)
                return None
        else:
            error = response.json() if response else "No response"
            results.add_fail("Create sales order", error)
            return None
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create customer", error)
        return None

def main():
    """Run all tests"""
    print("="*80)
    print("COMPREHENSIVE E2E TESTING WITH UNFK AND INVENTORY VERIFICATION")
    print("="*80)
    
    results = TestResults()
    tracker = InventoryTracker()
    
    # Run tests in order
    vendor_id = test_vendor_creation(results)
    item_id = test_item_creation(results, vendor_id, tracker)
    po_id = test_purchase_order_flow(results, vendor_id, item_id, tracker)
    lot_id = test_lot_check_in(results, po_id, item_id, tracker)
    
    # Test UNFK reverse check-in
    if lot_id:
        test_unfk_reverse_check_in(results, lot_id, item_id, tracker)
    
    # Re-check in lot for production test
    if po_id and item_id:
        po = PurchaseOrder.objects.get(id=po_id)
        lot_data = {
            'item_id': item_id,
            'vendor_lot_number': 'VENDOR-LOT-002',
            'quantity': 100,
            'received_date': datetime.now().isoformat(),
            'po_number': po.po_number,
            'status': 'accepted'
        }
        response = make_api_request('POST', '/lots/', lot_data)
        if response and response.status_code == 201:
            lot_id_2 = response.json().get('id')
            tracker.snapshot("After second check-in", item_id)
    
    # Test production batch
    batch_id = test_production_batch_flow(results, item_id, tracker)
    
    # Test UNFK batch
    if batch_id:
        fg_item = Item.objects.filter(item_type='finished_good', sku='FG001').first()
        if fg_item:
            test_unfk_batch(results, batch_id, item_id, fg_item.id, tracker)
    
    # Test invoice creation
    test_invoice_creation(results)
    
    # Print inventory history
    tracker.print_history()
    
    # Print summary
    results.print_summary()
    
    # Save results
    with open(BASE_DIR / 'e2e_test_results_with_unfk.txt', 'w') as f:
        f.write("="*80 + "\n")
        f.write("E2E TEST RESULTS WITH UNFK TESTING\n")
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
    
    print(f"\nResults saved to: {BASE_DIR / 'e2e_test_results_with_unfk.txt'}")

if __name__ == '__main__':
    main()
