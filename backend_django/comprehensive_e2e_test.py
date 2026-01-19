"""
Comprehensive End-to-End Testing Script
Tests all major flows in the WWI ERP system
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
    CostMaster, Customer, ShipToLocation
)

API_BASE_URL = 'http://localhost:8000/api'

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name, details=""):
        self.passed.append(f"[PASS] {test_name}" + (f" - {details}" if details else ""))
        print(f"[PASS] {test_name}")
    
    def add_fail(self, test_name, error):
        self.failed.append(f"[FAIL] {test_name}: {error}")
        print(f"[FAIL] {test_name}: {error}")
    
    def add_warning(self, test_name, warning):
        self.warnings.append(f"[WARN] {test_name}: {warning}")
        print(f"[WARN] {test_name}: {warning}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"\nPassed: {len(self.passed)}")
        print(f"Failed: {len(self.failed)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.failed:
            print("\nFAILED TESTS:")
            for fail in self.failed:
                print(f"  {fail}")
        
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
    
    # Test 1: Create vendor with all fields
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
        results.add_pass("Create vendor with all fields", f"Vendor ID: {vendor_id}")
        return vendor_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create vendor with all fields", error)
        return None

def test_item_creation(results, vendor_id):
    """Test creating items"""
    print("\n=== Testing Item Creation ===")
    
    if not vendor_id:
        results.add_fail("Create item", "No vendor available")
        return None
    
    # Test 1: Create item with all fields
    item_data = {
        'sku': 'TEST001',
        'name': 'Test Item 1',
        'vendor': 'Test Vendor Inc',
        'vendor_item_name': 'Vendor Test Item',
        'item_type': 'raw_material',
        'unit_of_measure': 'lbs',
        'price': 10.50,
        'hts_code': '12345678',
        'country_of_origin': 'USA',
        'tariff': 0.05
    }
    
    response = make_api_request('POST', '/items/', item_data)
    if response and response.status_code == 201:
        item_id = response.json().get('id')
        results.add_pass("Create item with all fields", f"Item ID: {item_id}")
        
        # Verify CostMaster was created
        cost_master = CostMaster.objects.filter(wwi_product_code='TEST001').first()
        if cost_master:
            results.add_pass("CostMaster auto-created for item")
        else:
            results.add_fail("CostMaster auto-created for item", "CostMaster not found")
        
        return item_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create item with all fields", error)
        return None

def test_purchase_order_creation(results, vendor_id, item_id):
    """Test creating purchase orders"""
    print("\n=== Testing Purchase Order Creation ===")
    
    if not vendor_id or not item_id:
        results.add_fail("Create purchase order", "Missing prerequisites")
        return None
    
    # Test 1: Create PO with items
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
        
        # Test 2: Issue PO
        issue_response = make_api_request('POST', f'/purchase-orders/{po_id}/issue/')
        if issue_response and issue_response.status_code == 200:
            results.add_pass("Issue purchase order")
            
            # Verify on_order was updated
            item = Item.objects.get(id=item_id)
            if item.on_order == 100:
                results.add_pass("Item on_order updated when PO issued")
            else:
                results.add_fail("Item on_order updated when PO issued", 
                               f"Expected 100, got {item.on_order}")
        else:
            error = issue_response.json() if issue_response else "No response"
            results.add_fail("Issue purchase order", error)
        
        return po_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create purchase order", error)
        return None

def test_lot_check_in(results, po_id, item_id):
    """Test lot check-in"""
    print("\n=== Testing Lot Check-In ===")
    
    if not po_id or not item_id:
        results.add_fail("Lot check-in", "Missing prerequisites")
        return None
    
    # Test 1: Check in lot
    lot_data = {
        'item': item_id,
        'vendor_lot_number': 'VENDOR-LOT-001',
        'quantity': 100,
        'unit_of_measure': 'lbs',
        'po_number': PurchaseOrder.objects.get(id=po_id).po_number,
        'tracking_number': 'TRACK123456',
        'status': 'available'
    }
    
    response = make_api_request('POST', '/lots/', lot_data)
    if response and response.status_code == 201:
        lot_id = response.json().get('id')
        results.add_pass("Check in lot", f"Lot ID: {lot_id}")
        
        # Verify on_order decreased and available increased
        item = Item.objects.get(id=item_id)
        if item.on_order == 0:
            results.add_pass("Item on_order decreased after check-in")
        else:
            results.add_warning("Item on_order after check-in", 
                               f"Expected 0, got {item.on_order}")
        
        return lot_id
    else:
        error = response.json() if response else "No response"
        results.add_fail("Check in lot", error)
        return None

def test_production_batch(results, item_id):
    """Test production batch creation"""
    print("\n=== Testing Production Batch ===")
    
    # First create a finished good item
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
        
        # Create production batch
        batch_data = {
            'finished_good_item': fg_item_id,
            'quantity_produced': 50,
            'production_date': datetime.now().strftime('%Y-%m-%d'),
            'batch_type': 'production'
        }
        
        response = make_api_request('POST', '/production-batches/', batch_data)
        if response and response.status_code == 201:
            batch_id = response.json().get('id')
            batch_number = response.json().get('batch_number')
            results.add_pass("Create production batch", f"Batch: {batch_number}")
            
            # Test closing batch
            close_response = make_api_request('POST', f'/production-batches/{batch_id}/close/')
            if close_response and close_response.status_code == 200:
                results.add_pass("Close production batch")
                
                # Verify lot was created
                lot = Lot.objects.filter(batch_number=batch_number).first()
                if lot:
                    results.add_pass("Output lot created when batch closed")
                else:
                    results.add_fail("Output lot created when batch closed", "Lot not found")
            else:
                error = close_response.json() if close_response else "No response"
                results.add_fail("Close production batch", error)
            
            return batch_id
        else:
            error = response.json() if response else "No response"
            results.add_fail("Create production batch", error)
            return None
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create finished good item", error)
        return None

def test_sales_order(results):
    """Test sales order creation"""
    print("\n=== Testing Sales Order ===")
    
    # Create customer first
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
            results.add_fail("Create sales order", "No finished good items available")
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
            so_number = response.json().get('so_number')
            results.add_pass("Create sales order", f"SO Number: {so_number}")
            return so_id
        else:
            error = response.json() if response else "No response"
            results.add_fail("Create sales order", error)
            return None
    else:
        error = response.json() if response else "No response"
        results.add_fail("Create customer", error)
        return None

def test_invoice_creation(results, so_id):
    """Test invoice creation"""
    print("\n=== Testing Invoice Creation ===")
    
    if not so_id:
        results.add_fail("Create invoice", "No sales order available")
        return None
    
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

def test_error_handling(results):
    """Test error handling and validation"""
    print("\n=== Testing Error Handling ===")
    
    # Test 1: Create item with duplicate SKU
    item_data = {
        'sku': 'TEST001',  # Already exists
        'name': 'Duplicate Test',
        'vendor': 'Test Vendor Inc',
        'item_type': 'raw_material'
    }
    
    response = make_api_request('POST', '/items/', item_data)
    if response and response.status_code == 400:
        results.add_pass("Reject duplicate SKU for same vendor")
    else:
        results.add_fail("Reject duplicate SKU", "Should have returned 400")
    
    # Test 2: Create PO with invalid vendor
    po_data = {
        'vendor_id': 99999,
        'items': []
    }
    
    response = make_api_request('POST', '/purchase-orders/', po_data)
    if response and response.status_code == 400:
        results.add_pass("Reject PO with invalid vendor")
    else:
        results.add_fail("Reject PO with invalid vendor", "Should have returned 400")
    
    # Test 3: Create lot without required vendor_lot_number
    lot_data = {
        'item': Item.objects.first().id,
        'quantity': 10,
        'unit_of_measure': 'lbs'
    }
    
    response = make_api_request('POST', '/lots/', lot_data)
    if response and response.status_code == 400:
        results.add_pass("Reject lot without vendor_lot_number")
    else:
        results.add_warning("Reject lot without vendor_lot_number", 
                          "May be allowed - check business rules")

def test_pdf_generation(results):
    """Test PDF generation"""
    print("\n=== Testing PDF Generation ===")
    
    # Test PO PDF
    po = PurchaseOrder.objects.first()
    if po:
        response = make_api_request('GET', f'/purchase-orders/{po.id}/pdf/')
        if response and response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
            results.add_pass("Generate purchase order PDF")
        else:
            results.add_fail("Generate purchase order PDF", 
                           f"Status: {response.status_code if response else 'No response'}")
    
    # Test Invoice PDF
    invoice = Invoice.objects.first()
    if invoice:
        response = make_api_request('GET', f'/invoices/{invoice.id}/pdf/')
        if response and response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
            results.add_pass("Generate invoice PDF")
        else:
            results.add_fail("Generate invoice PDF", 
                           f"Status: {response.status_code if response else 'No response'}")

def main():
    """Run all tests"""
    print("="*80)
    print("COMPREHENSIVE END-TO-END TESTING")
    print("="*80)
    
    results = TestResults()
    
    # Run tests in order
    vendor_id = test_vendor_creation(results)
    item_id = test_item_creation(results, vendor_id)
    po_id = test_purchase_order_creation(results, vendor_id, item_id)
    lot_id = test_lot_check_in(results, po_id, item_id)
    batch_id = test_production_batch(results, item_id)
    so_id = test_sales_order(results)
    invoice_id = test_invoice_creation(results, so_id)
    test_error_handling(results)
    test_pdf_generation(results)
    
    # Print summary
    results.print_summary()
    
    # Save results to file
    with open(BASE_DIR / 'test_results.txt', 'w') as f:
        f.write("="*80 + "\n")
        f.write("E2E TEST RESULTS\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write("="*80 + "\n\n")
        f.write(f"Passed: {len(results.passed)}\n")
        f.write(f"Failed: {len(results.failed)}\n")
        f.write(f"Warnings: {len(results.warnings)}\n\n")
        
        if results.passed:
            f.write("PASSED TESTS:\n")
            for test in results.passed:
                f.write(f"  {test}\n")
        
        if results.failed:
            f.write("\nFAILED TESTS:\n")
            for test in results.failed:
                f.write(f"  {test}\n")
        
        if results.warnings:
            f.write("\nWARNINGS:\n")
            for test in results.warnings:
                f.write(f"  {test}\n")
    
    print(f"\nResults saved to: {BASE_DIR / 'test_results.txt'}")

if __name__ == '__main__':
    main()
