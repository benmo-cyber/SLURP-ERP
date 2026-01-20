"""
Check for duplicate or orphaned transactions for batch BT-20260119-002
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import InventoryTransaction, ProductionBatch, Lot, Item
from django.db import connection

batch_number = 'BT-20260119-002'
item_sku = 'D1300K0010'

print("="*80)
print(f"CHECKING FOR DUPLICATE/ORPHANED TRANSACTIONS")
print("="*80)

# Get the batch
batch = ProductionBatch.objects.get(batch_number=batch_number)
print(f"\nBatch: {batch.batch_number} (ID: {batch.id})")
print(f"Status: {batch.status}")

# Get all transactions for this batch
print(f"\nALL TRANSACTIONS FOR BATCH {batch_number}:")
all_txns = InventoryTransaction.objects.filter(reference_number=batch_number).order_by('transaction_date', 'id')
for txn in all_txns:
    print(f"  ID: {txn.id} | {txn.transaction_date} | {txn.transaction_type} | Lot: {txn.lot.lot_number} | Qty: {txn.quantity:+.2f} | {txn.notes}")

# Get item and lot
item = Item.objects.get(sku=item_sku)
lot = Lot.objects.filter(item=item).first()

if lot:
    print(f"\nALL TRANSACTIONS FOR LOT {lot.lot_number} ({item_sku}):")
    lot_txns = InventoryTransaction.objects.filter(lot=lot).order_by('transaction_date', 'id')
    total = 0.0
    for txn in lot_txns:
        print(f"  ID: {txn.id} | {txn.transaction_date} | {txn.transaction_type} | Qty: {txn.quantity:+.2f} | Ref: {txn.reference_number} | {txn.notes}")
        total += txn.quantity
    
    print(f"\n  Sum of all transactions: {total:+.2f}")
    print(f"  Lot quantity: {lot.quantity}")
    print(f"  Lot remaining: {lot.quantity_remaining}")
    print(f"  Expected remaining: {lot.quantity + total}")
    print(f"  Discrepancy: {lot.quantity_remaining - (lot.quantity + total)}")

# Check for transactions with same reference but different quantities
print(f"\nCHECKING FOR MULTIPLE TRANSACTIONS WITH SAME REFERENCE:")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT reference_number, lot_id, transaction_type, COUNT(*) as count, 
               SUM(quantity) as total_qty, GROUP_CONCAT(id) as txn_ids
        FROM erp_core_inventorytransaction
        WHERE reference_number = ?
        GROUP BY reference_number, lot_id, transaction_type
        HAVING COUNT(*) > 1
    """, [batch_number])
    
    duplicates = cursor.fetchall()
    if duplicates:
        print("  FOUND DUPLICATE TRANSACTIONS!")
        for dup in duplicates:
            print(f"    Ref: {dup[0]} | Lot ID: {dup[1]} | Type: {dup[2]} | Count: {dup[3]} | Total: {dup[4]} | IDs: {dup[5]}")
    else:
        print("  No duplicate transactions found")

# Check batch inputs vs transactions
print(f"\nBATCH INPUTS vs TRANSACTIONS:")
for batch_input in batch.inputs.all():
    lot = batch_input.lot
    if lot.item.sku == item_sku:
        txn_total = InventoryTransaction.objects.filter(
            reference_number=batch_number,
            lot=lot,
            transaction_type__in=['production_input', 'repack_input']
        ).aggregate(total=models.Sum('quantity'))['total'] or 0.0
        
        print(f"  Lot: {lot.lot_number}")
        print(f"    Batch Input: {batch_input.quantity_used}")
        print(f"    Transaction Total: {abs(txn_total)}")
        print(f"    Difference: {abs(batch_input.quantity_used - abs(txn_total))}")
