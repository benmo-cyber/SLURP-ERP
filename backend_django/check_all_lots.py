"""
Check all lots for D1300K0010 and all batches using it
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import Lot, Item, ProductionBatchInput, InventoryTransaction
from django.db import connection

# Find all lots for D1300K0010
item = Item.objects.get(sku='D1300K0010')
print(f"Item: {item.name} ({item.sku})")
print("="*80)

# Get ALL lots (including rejected/on_hold)
all_lots = Lot.objects.filter(item=item).order_by('received_date')
print(f"\nALL LOTS (all statuses):")
total_received = 0.0
total_remaining = 0.0

for lot in all_lots:
    print(f"  Lot: {lot.lot_number} | Status: {lot.status}")
    print(f"    Original: {lot.quantity} | Remaining: {lot.quantity_remaining}")
    print(f"    Received: {lot.received_date}")
    total_received += lot.quantity
    total_remaining += lot.quantity_remaining

print(f"\n  TOTAL RECEIVED: {total_received}")
print(f"  TOTAL REMAINING: {total_remaining}")
print(f"  TOTAL CONSUMED: {total_received - total_remaining}")

# Check all batch inputs
print(f"\nALL BATCH INPUTS FOR D1300K0010:")
batch_inputs = ProductionBatchInput.objects.filter(lot__item=item).select_related('batch', 'lot').order_by('batch__batch_number', 'id')
total_in_batches = 0.0

for bi in batch_inputs:
    print(f"  Batch: {bi.batch.batch_number} ({bi.batch.status}) | Lot: {bi.lot.lot_number} | Qty: {bi.quantity_used}")
    total_in_batches += bi.quantity_used

print(f"\n  TOTAL IN BATCHES: {total_in_batches}")

# Check all transactions
print(f"\nALL TRANSACTIONS FOR D1300K0010:")
transactions = InventoryTransaction.objects.filter(lot__item=item).order_by('transaction_date', 'id')
txn_sum = 0.0

for txn in transactions:
    print(f"  {txn.transaction_date} | {txn.transaction_type} | Lot: {txn.lot.lot_number} | Qty: {txn.quantity:+.2f} | Ref: {txn.reference_number}")
    txn_sum += txn.quantity

print(f"\n  SUM OF TRANSACTIONS: {txn_sum}")
print(f"  EXPECTED REMAINING: {total_received + txn_sum}")
print(f"  ACTUAL REMAINING: {total_remaining}")
print(f"  DISCREPANCY: {total_remaining - (total_received + txn_sum)}")

# Check for batches that might have been updated
print(f"\nCHECKING FOR BATCH UPDATE ISSUES:")
print("Looking for batches where inputs were updated (potential double-counting)...")

# Get all batches using this item
batches = set(bi.batch for bi in batch_inputs)
for batch in batches:
    inputs = ProductionBatchInput.objects.filter(batch=batch, lot__item=item)
    transactions = InventoryTransaction.objects.filter(reference_number=batch.batch_number, lot__item=item)
    
    input_total = sum(i.quantity_used for i in inputs)
    txn_total = abs(sum(t.quantity for t in transactions if t.quantity < 0))
    
    if abs(input_total - txn_total) > 0.01:
        print(f"  WARNING: Batch {batch.batch_number}")
        print(f"    Input total: {input_total}")
        print(f"    Transaction total: {txn_total}")
        print(f"    Difference: {abs(input_total - txn_total)}")
