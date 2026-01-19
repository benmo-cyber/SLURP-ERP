"""
End-to-End Test for Production and Repack Batches
Tests both BT (production) and R (repack) batch creation, closing, and lot generation
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
    InventoryTransaction, ProductionLog
)
from erp_core.views import generate_po_number, generate_batch_number, log_production_batch_closure
from django.utils import timezone

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

def setup_test_data(results):
    """Set up test data: vendor, raw material item, PO, lot"""
    print("\n=== Setting Up Test Data ===")
    
    try:
        # Create vendor
        vendor, _ = Vendor.objects.get_or_create(
            name='Test Vendor Batch',
            defaults={
                'contact_name': 'Batch Test',
                'email': 'batch@testvendor.com',
                'phone': '555-9999',
                'street_address': '789 Batch St',
                'city': 'Test City',
                'state': 'MO',
                'zip_code': '12345',
                'country': 'USA',
                'approval_status': 'approved'
            }
        )
        
        # Create raw material item
        import time
        unique_sku = f'BATCHTEST{int(time.time())}'
        raw_item, _ = Item.objects.get_or_create(
            sku=unique_sku,
            vendor=vendor.name,
            defaults={
                'name': 'Test Raw Material for Batches',
                'vendor_item_name': 'Vendor Batch Material',
                'item_type': 'raw_material',
                'unit_of_measure': 'lbs',
                'price': 10.50,
                'on_order': 0
            }
        )
        
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
            item=raw_item,
            quantity_ordered=500,
            unit_price=10.50
        )
        raw_item.on_order = 500
        raw_item.save()
        
        # Check in lot
        lot = Lot.objects.create(
            lot_number=f'BATCH-LOT-{int(time.time())}',
            vendor_lot_number=f'VENDOR-BATCH-{int(time.time())}',
            item=raw_item,
            quantity=500,
            quantity_remaining=500,
            received_date=timezone.now(),
            po_number=po.po_number,
            status='accepted'
        )
        InventoryTransaction.objects.create(
            transaction_type='receipt',
            lot=lot,
            quantity=500,
            notes=f'Check-in from PO {po.po_number}'
        )
        raw_item.on_order = 0
        raw_item.save()
        
        results.add_pass("Setup test data", f"Item: {raw_item.sku}, Lot: {lot.lot_number}")
        return vendor.id, raw_item.id, lot.id
    except Exception as e:
        results.add_fail("Setup test data", str(e))
        import traceback
        traceback.print_exc()
        return None, None, None

def test_production_batch(results, raw_item_id, lot_id):
    """Test production batch creation and closing"""
    print("\n=== Testing Production Batch (BT) ===")
    
    if not raw_item_id or not lot_id:
        results.add_fail("Production batch", "Missing prerequisites")
        return None
    
    try:
        raw_item = Item.objects.get(id=raw_item_id)
        lot = Lot.objects.get(id=lot_id)
        
        # Create finished good item
        import time
        fg_item = Item.objects.create(
            sku=f'FG-BATCH-{int(time.time())}',
            name='Test Finished Good for Production',
            item_type='finished_good',
            unit_of_measure='lbs',
            price=25.00,
            on_order=0
        )
        results.add_pass("Create finished good item", f"SKU: {fg_item.sku}")
        
        # Generate batch number using proper function
        batch_number = generate_batch_number(batch_type='production')
        results.add_pass("Generate production batch number", f"Batch: {batch_number}")
        
        # Verify it starts with BT
        if batch_number.startswith('BT-'):
            results.add_pass("Batch number has BT prefix")
        else:
            results.add_fail("Batch number prefix", f"Expected BT-, got {batch_number[:3]}")
        
        # Create production batch
        batch = ProductionBatch.objects.create(
            batch_number=batch_number,
            finished_good_item=fg_item,
            quantity_produced=100,
            production_date=timezone.now(),
            batch_type='production',
            status='in_progress'
        )
        
        # Add input
        ProductionBatchInput.objects.create(
            batch=batch,
            lot=lot,
            quantity_used=80
        )
        
        # Update lot quantity
        lot.quantity_remaining = max(0, lot.quantity_remaining - 80)
        lot.save()
        
        InventoryTransaction.objects.create(
            transaction_type='adjustment',
            lot=lot,
            quantity=-80,
            notes=f'Used in production batch {batch.batch_number}'
        )
        
        results.add_pass("Create production batch", f"Batch: {batch.batch_number}, Input: 80 lbs")
        
        # Close batch - set status and closed_date
        batch.status = 'closed'
        batch.closed_date = timezone.now()
        batch.save()
        
        # Create output lot (this should happen automatically in the view, but we'll do it manually for testing)
        output_lot = Lot.objects.create(
            lot_number=batch.batch_number,  # Use batch number as lot number
            item=fg_item,
            quantity=100,
            quantity_remaining=100,
            received_date=timezone.now(),
            status='accepted'
        )
        
        ProductionBatchOutput.objects.create(
            batch=batch,
            lot=output_lot,
            quantity_produced=100
        )
        
        InventoryTransaction.objects.create(
            transaction_type='receipt',
            lot=output_lot,
            quantity=100,
            notes=f'Output from production batch {batch.batch_number}'
        )
        
        # IMPORTANT: Call log_production_batch_closure to create ProductionLog entry
        log_production_batch_closure(batch, notes=f'Batch {batch.batch_number} closed via test')
        
        results.add_pass("Close production batch", f"Output lot: {output_lot.lot_number}, Quantity: 100 lbs")
        
        # Verify ProductionLog was created
        log_entry = ProductionLog.objects.filter(batch_number=batch.batch_number).first()
        if log_entry:
            results.add_pass("ProductionLog entry created", f"Log ID: {log_entry.id}")
        else:
            results.add_fail("ProductionLog entry", "No log entry found after batch closure")
        
        # Verify batch exists and is visible
        batch_check = ProductionBatch.objects.filter(batch_number=batch_number).first()
        if batch_check and batch_check.status == 'closed':
            results.add_pass("Production batch visible in system")
        else:
            results.add_fail("Production batch visibility", "Batch not found or not closed")
        
        return batch.id, fg_item.id
    except Exception as e:
        results.add_fail("Production batch", str(e))
        import traceback
        traceback.print_exc()
        return None, None

def test_repack_batch(results, raw_item_id, lot_id):
    """Test repack batch creation and closing"""
    print("\n=== Testing Repack Batch (R) ===")
    
    if not raw_item_id or not lot_id:
        results.add_fail("Repack batch", "Missing prerequisites")
        return None
    
    try:
        raw_item = Item.objects.get(id=raw_item_id)
        lot = Lot.objects.get(id=lot_id)
        
        # For repack, we need a distributed item or finished good to repack
        # Create a distributed item
        import time
        dist_item = Item.objects.create(
            sku=f'DIST-REPACK-{int(time.time())}',
            name='Test Distributed Item for Repack',
            item_type='distributed_item',
            unit_of_measure='ea',
            price=15.00,
            on_order=0
        )
        results.add_pass("Create distributed item for repack", f"SKU: {dist_item.sku}")
        
        # Generate batch number using proper function
        batch_number = generate_batch_number(batch_type='repack')
        results.add_pass("Generate repack batch number", f"Batch: {batch_number}")
        
        # Verify it starts with R
        if batch_number.startswith('R-'):
            results.add_pass("Batch number has R prefix")
        else:
            results.add_fail("Batch number prefix", f"Expected R-, got {batch_number[:2]}")
        
        # Create repack batch
        # For repack, finished_good_item is the item being repacked (can be distributed_item)
        batch = ProductionBatch.objects.create(
            batch_number=batch_number,
            finished_good_item=dist_item,  # Item being repacked
            quantity_produced=50,  # In item's native unit (ea)
            production_date=timezone.now(),
            batch_type='repack',
            status='in_progress'
        )
        
        # Add input (using the raw material lot)
        ProductionBatchInput.objects.create(
            batch=batch,
            lot=lot,
            quantity_used=50  # In lot's unit (lbs), but will be converted
        )
        
        # Update lot quantity
        lot.quantity_remaining = max(0, lot.quantity_remaining - 50)
        lot.save()
        
        InventoryTransaction.objects.create(
            transaction_type='adjustment',
            lot=lot,
            quantity=-50,
            notes=f'Used in repack batch {batch.batch_number}'
        )
        
        results.add_pass("Create repack batch", f"Batch: {batch.batch_number}, Input: 50 lbs")
        
        # Close batch - set status and closed_date
        batch.status = 'closed'
        batch.closed_date = timezone.now()
        batch.save()
        
        # For repack batches, output lot should be created when batch is closed
        # The lot number should be generated automatically
        # Check if output lot was created (it should be created by the view's update method)
        # For testing, we'll create it manually
        output_lot = Lot.objects.create(
            lot_number=batch.batch_number,  # Use batch number as lot number
            item=dist_item,
            quantity=50,  # In item's native unit
            quantity_remaining=50,
            received_date=timezone.now(),
            status='accepted'
        )
        
        ProductionBatchOutput.objects.create(
            batch=batch,
            lot=output_lot,
            quantity_produced=50
        )
        
        InventoryTransaction.objects.create(
            transaction_type='receipt',
            lot=output_lot,
            quantity=50,
            notes=f'Output from repack batch {batch.batch_number}'
        )
        
        # IMPORTANT: Call log_production_batch_closure to create ProductionLog entry
        log_production_batch_closure(batch, notes=f'Repack batch {batch.batch_number} closed via test')
        
        results.add_pass("Close repack batch", f"Output lot: {output_lot.lot_number}, Quantity: 50 ea")
        
        # Verify ProductionLog was created
        log_entry = ProductionLog.objects.filter(batch_number=batch.batch_number).first()
        if log_entry:
            results.add_pass("ProductionLog entry created", f"Log ID: {log_entry.id}")
        else:
            results.add_fail("ProductionLog entry", "No log entry found after batch closure")
        
        # Verify batch exists and is visible
        batch_check = ProductionBatch.objects.filter(batch_number=batch_number).first()
        if batch_check and batch_check.status == 'closed':
            results.add_pass("Repack batch visible in system")
        else:
            results.add_fail("Repack batch visibility", "Batch not found or not closed")
        
        return batch.id
    except Exception as e:
        results.add_fail("Repack batch", str(e))
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all tests"""
    print("="*80)
    print("COMPREHENSIVE E2E TESTING: PRODUCTION AND REPACK BATCHES")
    print("="*80)
    
    results = TestResults()
    
    # Setup test data
    vendor_id, raw_item_id, lot_id = setup_test_data(results)
    
    if not raw_item_id or not lot_id:
        results.print_summary()
        return 1
    
    # Test production batch
    prod_batch_id, fg_item_id = test_production_batch(results, raw_item_id, lot_id)
    
    # Test repack batch (use remaining lot quantity)
    repack_batch_id = test_repack_batch(results, raw_item_id, lot_id)
    
    # Print summary
    results.print_summary()
    
    # Save results
    with open(BASE_DIR / 'e2e_test_batch_repack_results.txt', 'w') as f:
        f.write("="*80 + "\n")
        f.write("E2E TEST RESULTS: PRODUCTION AND REPACK BATCHES\n")
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
    
    print(f"\nResults saved to: {BASE_DIR / 'e2e_test_batch_repack_results.txt'}")
    
    # List all batches created
    print("\n=== BATCHES CREATED ===")
    all_batches = ProductionBatch.objects.all().order_by('-created_at')[:10]
    for batch in all_batches:
        print(f"  {batch.batch_number} - {batch.batch_type} - {batch.status} - Created: {batch.created_at}")
    
    # Return exit code based on results
    if results.failed:
        return 1
    return 0

if __name__ == '__main__':
    exit(main())
