"""
Investigate batch BT-20260119-002 and inventory discrepancies for D1300K0010
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.db import connection
from erp_core.models import (
    ProductionBatch, ProductionBatchInput, ProductionBatchOutput,
    Lot, InventoryTransaction, Item
)

def investigate_batch(batch_number):
    """Investigate a specific batch"""
    print("="*80)
    print(f"INVESTIGATING BATCH: {batch_number}")
    print("="*80)
    
    try:
        batch = ProductionBatch.objects.get(batch_number=batch_number)
    except ProductionBatch.DoesNotExist:
        print(f"ERROR: Batch {batch_number} not found")
        return
    
    print(f"\nBatch Details:")
    print(f"  ID: {batch.id}")
    print(f"  Type: {batch.batch_type}")
    print(f"  Status: {batch.status}")
    print(f"  Quantity Produced: {batch.quantity_produced}")
    print(f"  Quantity Actual: {batch.quantity_actual}")
    print(f"  Spills: {batch.spills}")
    print(f"  Wastes: {batch.wastes}")
    print(f"  Variance: {batch.variance}")
    
    # Check inputs
    print(f"\nInputs:")
    total_input = 0.0
    for input_item in batch.inputs.all():
        lot = input_item.lot
        print(f"  Lot: {lot.lot_number} ({lot.item.sku})")
        print(f"    Quantity Used: {input_item.quantity_used}")
        print(f"    Lot Quantity Remaining: {lot.quantity_remaining}")
        print(f"    Lot Original Quantity: {lot.quantity}")
        total_input += input_item.quantity_used
    
    print(f"\n  Total Input: {total_input}")
    print(f"  Quantity Actual: {batch.quantity_actual}")
    print(f"  Difference: {abs(total_input - batch.quantity_actual)}")
    
    # Check outputs
    print(f"\nOutputs:")
    for output in batch.outputs.all():
        lot = output.lot
        print(f"  Lot: {lot.lot_number} ({lot.item.sku})")
        print(f"    Quantity Produced: {output.quantity_produced}")
        print(f"    Lot Quantity: {lot.quantity}")
        print(f"    Lot Quantity Remaining: {lot.quantity_remaining}")
    
    # Check all inventory transactions for this batch
    print(f"\nInventory Transactions for this batch:")
    transactions = InventoryTransaction.objects.filter(reference_number=batch_number).order_by('transaction_date')
    for txn in transactions:
        print(f"  {txn.transaction_date} | {txn.transaction_type} | Lot: {txn.lot.lot_number} | Qty: {txn.quantity} | {txn.notes}")
    
    return batch

def investigate_item_inventory(sku):
    """Investigate inventory for a specific item"""
    print("\n" + "="*80)
    print(f"INVESTIGATING ITEM: {sku}")
    print("="*80)
    
    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        print(f"ERROR: Item {sku} not found")
        return
    
    print(f"\nItem: {item.name} ({item.sku})")
    
    # Get all lots for this item
    lots = Lot.objects.filter(item=item, status='accepted').order_by('received_date')
    print(f"\nAll Lots for {sku}:")
    total_received = 0.0
    total_remaining = 0.0
    
    for lot in lots:
        print(f"  Lot: {lot.lot_number}")
        print(f"    Original Quantity: {lot.quantity}")
        print(f"    Quantity Remaining: {lot.quantity_remaining}")
        print(f"    Received Date: {lot.received_date}")
        total_received += lot.quantity
        total_remaining += lot.quantity_remaining
    
    print(f"\n  Total Received: {total_received}")
    print(f"  Total Remaining: {total_remaining}")
    print(f"  Total Consumed: {total_received - total_remaining}")
    
    # Get all inventory transactions for this item
    print(f"\nAll Inventory Transactions for {sku}:")
    transactions = InventoryTransaction.objects.filter(lot__item=item).order_by('transaction_date', 'id')
    
    total_transactions = 0.0
    for txn in transactions:
        print(f"  {txn.transaction_date} | {txn.transaction_type} | Lot: {txn.lot.lot_number} | Qty: {txn.quantity:+.2f} | Ref: {txn.reference_number} | {txn.notes}")
        total_transactions += txn.quantity
    
    print(f"\n  Sum of all transactions: {total_transactions}")
    print(f"  Expected remaining: {total_received + total_transactions}")
    print(f"  Actual remaining: {total_remaining}")
    print(f"  Discrepancy: {total_remaining - (total_received + total_transactions)}")
    
    # Check for duplicate transactions
    print(f"\nChecking for duplicate transactions:")
    lot_ids = list(lots.values_list('id', flat=True))
    if lot_ids:
        placeholders = ','.join(['?'] * len(lot_ids))
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT transaction_type, lot_id, quantity, reference_number, COUNT(*) as count
                FROM erp_core_inventorytransaction
                WHERE lot_id IN ({placeholders})
                GROUP BY transaction_type, lot_id, quantity, reference_number
                HAVING COUNT(*) > 1
            """, lot_ids)
            
            duplicates = cursor.fetchall()
            if duplicates:
                print("  WARNING: Found duplicate transactions!")
                for dup in duplicates:
                    print(f"    {dup}")
            else:
                print("  No duplicate transactions found")
    
    # Check production batch inputs
    print(f"\nProduction Batch Inputs for {sku}:")
    batch_inputs = ProductionBatchInput.objects.filter(lot__item=item).select_related('batch', 'lot').order_by('batch__batch_number')
    total_used_in_batches = 0.0
    batch_totals = {}
    for batch_input in batch_inputs:
        batch_num = batch_input.batch.batch_number
        if batch_num not in batch_totals:
            batch_totals[batch_num] = 0.0
        batch_totals[batch_num] += batch_input.quantity_used
        total_used_in_batches += batch_input.quantity_used
        print(f"  Batch: {batch_input.batch.batch_number} ({batch_input.batch.status}) | Lot: {batch_input.lot.lot_number} | Qty: {batch_input.quantity_used}")
    
    print(f"\n  Total Used in Batches: {total_used_in_batches}")
    print(f"\n  Per-Batch Totals:")
    for batch_num, total in batch_totals.items():
        print(f"    {batch_num}: {total} lbs")
    
    # Check if there are multiple transactions for the same batch (potential double-counting)
    print(f"\nChecking for multiple transactions per batch:")
    with connection.cursor() as cursor:
        if lot_ids:
            placeholders = ','.join(['?'] * len(lot_ids))
            cursor.execute(f"""
                SELECT reference_number, lot_id, COUNT(*) as count, SUM(quantity) as total_qty
                FROM erp_core_inventorytransaction
                WHERE lot_id IN ({placeholders})
                  AND transaction_type = 'production_input'
                  AND reference_number IS NOT NULL
                GROUP BY reference_number, lot_id
                HAVING COUNT(*) > 1
            """, lot_ids)
            
            multi_txns = cursor.fetchall()
            if multi_txns:
                print("  WARNING: Found batches with multiple transactions for the same lot!")
                for txn in multi_txns:
                    print(f"    Batch: {txn[0]} | Lot ID: {txn[1]} | Transaction Count: {txn[2]} | Total Qty: {txn[3]}")
            else:
                print("  No duplicate batch transactions found")
    
    return item

if __name__ == '__main__':
    # Investigate the specific batch
    batch = investigate_batch('BT-20260119-002')
    
    # Investigate the item
    item = investigate_item_inventory('D1300K0010')
    
    print("\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80)
