"""
Audit and fix inventory discrepancies
- Find batches with mismatched inputs/outputs
- Find duplicate transactions
- Fix lot quantities
- Report all issues
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.db import connection, transaction
from erp_core.models import (
    ProductionBatch, ProductionBatchInput, ProductionBatchOutput,
    Lot, InventoryTransaction, Item
)
from decimal import Decimal

def audit_batch_inputs_outputs():
    """Find batches where inputs don't match outputs"""
    print("="*80)
    print("AUDITING BATCH INPUTS vs OUTPUTS")
    print("="*80)
    
    issues = []
    
    for batch in ProductionBatch.objects.filter(status='closed').select_related('finished_good_item'):
        total_input = sum(inp.quantity_used for inp in batch.inputs.all())
        
        # Expected output based on formula (rough check - inputs should roughly match output)
        # For now, just check if inputs + wastes + spills ≈ quantity_actual
        expected_min = batch.quantity_actual - (batch.wastes or 0) - (batch.spills or 0) - 50  # Allow some variance
        expected_max = batch.quantity_actual + 50
        
        if total_input < expected_min or total_input > expected_max:
            issues.append({
                'type': 'input_output_mismatch',
                'batch': batch.batch_number,
                'total_input': total_input,
                'quantity_actual': batch.quantity_actual,
                'wastes': batch.wastes or 0,
                'spills': batch.spills or 0,
                'difference': abs(total_input - batch.quantity_actual)
            })
            print(f"\nWARNING: Batch {batch.batch_number}")
            print(f"  Total Input: {total_input} lbs")
            print(f"  Quantity Actual: {batch.quantity_actual} lbs")
            print(f"  Difference: {abs(total_input - batch.quantity_actual)} lbs")
    
    return issues

def audit_duplicate_transactions():
    """Find duplicate or orphaned inventory transactions"""
    print("\n" + "="*80)
    print("AUDITING DUPLICATE TRANSACTIONS")
    print("="*80)
    
    issues = []
    
    # Check for multiple transactions for same batch/lot
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT reference_number, lot_id, transaction_type, COUNT(*) as count, 
                   SUM(quantity) as total_qty, GROUP_CONCAT(id) as txn_ids
            FROM erp_core_inventorytransaction
            WHERE reference_number IS NOT NULL
              AND transaction_type IN ('production_input', 'repack_input')
            GROUP BY reference_number, lot_id, transaction_type
            HAVING COUNT(*) > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"\nFound {len(duplicates)} duplicate transaction groups:")
            for dup in duplicates:
                ref, lot_id, txn_type, count, total_qty, txn_ids = dup
                lot = Lot.objects.get(id=lot_id)
                issues.append({
                    'type': 'duplicate_transaction',
                    'reference': ref,
                    'lot': lot.lot_number,
                    'count': count,
                    'total_qty': total_qty,
                    'transaction_ids': [int(x) for x in txn_ids.split(',')]
                })
                print(f"  Batch: {ref} | Lot: {lot.lot_number} | Count: {count} | Total: {total_qty}")
        else:
            print("No duplicate transactions found")
    
    return issues

def audit_lot_quantities():
    """Audit lot quantities against transactions"""
    print("\n" + "="*80)
    print("AUDITING LOT QUANTITIES")
    print("="*80)
    
    issues = []
    
    for lot in Lot.objects.filter(status='accepted').select_related('item'):
        transactions = InventoryTransaction.objects.filter(lot=lot)
        txn_sum = sum(txn.quantity for txn in transactions)
        
        expected_remaining = lot.quantity + txn_sum
        discrepancy = lot.quantity_remaining - expected_remaining
        
        if abs(discrepancy) > 0.01:  # More than 0.01 lbs difference
            issues.append({
                'type': 'lot_quantity_mismatch',
                'lot': lot.lot_number,
                'item': lot.item.sku,
                'original_qty': lot.quantity,
                'current_remaining': lot.quantity_remaining,
                'expected_remaining': expected_remaining,
                'discrepancy': discrepancy,
                'txn_sum': txn_sum
            })
            print(f"\nWARNING: Lot {lot.lot_number} ({lot.item.sku})")
            print(f"  Original: {lot.quantity} lbs")
            print(f"  Current Remaining: {lot.quantity_remaining} lbs")
            print(f"  Transaction Sum: {txn_sum} lbs")
            print(f"  Expected Remaining: {expected_remaining} lbs")
            print(f"  Discrepancy: {discrepancy} lbs")
    
    return issues

def fix_duplicate_transactions(issues):
    """Fix duplicate transactions by keeping only the most recent one"""
    print("\n" + "="*80)
    print("FIXING DUPLICATE TRANSACTIONS")
    print("="*80)
    
    fixed = 0
    
    for issue in issues:
        if issue['type'] != 'duplicate_transaction':
            continue
        
        txn_ids = issue['transaction_ids']
        if len(txn_ids) < 2:
            continue
        
        # Get all transactions
        transactions = InventoryTransaction.objects.filter(id__in=txn_ids).order_by('-transaction_date', '-id')
        
        if len(transactions) < 2:
            continue
        
        # Keep the most recent one
        keep_txn = transactions[0]
        delete_txns = transactions[1:]
        
        # Delete the older duplicates
        for txn in delete_txns:
            print(f"  Deleting duplicate transaction ID {txn.id} (keeping ID {keep_txn.id})")
            txn.delete()
            fixed += 1
    
    print(f"\nFixed {fixed} duplicate transactions")
    return fixed

def fix_lot_quantities(issues):
    """Fix lot quantity discrepancies"""
    print("\n" + "="*80)
    print("FIXING LOT QUANTITY DISCREPANCIES")
    print("="*80)
    
    fixed = 0
    
    with transaction.atomic():
        for issue in issues:
            if issue['type'] != 'lot_quantity_mismatch':
                continue
            
            try:
                lot = Lot.objects.get(lot_number=issue['lot'])
                
                # Recalculate from transactions
                transactions = InventoryTransaction.objects.filter(lot=lot)
                txn_sum = sum(txn.quantity for txn in transactions)
                correct_remaining = lot.quantity + txn_sum
                
                old_remaining = lot.quantity_remaining
                lot.quantity_remaining = round(correct_remaining, 2)
                lot.save()
                
                print(f"  Fixed lot {lot.lot_number}: {old_remaining} -> {lot.quantity_remaining} lbs")
                fixed += 1
            except Lot.DoesNotExist:
                print(f"  ERROR: Lot {issue['lot']} not found")
    
    print(f"\nFixed {fixed} lot quantity discrepancies")
    return fixed

def main():
    """Run full audit and fix"""
    print("="*80)
    print("INVENTORY AUDIT AND FIX")
    print("="*80)
    
    all_issues = []
    
    # Run audits
    all_issues.extend(audit_batch_inputs_outputs())
    all_issues.extend(audit_duplicate_transactions())
    all_issues.extend(audit_lot_quantities())
    
    # Summary
    print("\n" + "="*80)
    print("AUDIT SUMMARY")
    print("="*80)
    print(f"Total issues found: {len(all_issues)}")
    
    issue_types = {}
    for issue in all_issues:
        issue_type = issue['type']
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    
    for issue_type, count in issue_types.items():
        print(f"  {issue_type}: {count}")
    
    # Fix issues
    if all_issues:
        print("\n" + "="*80)
        print("FIXING ISSUES")
        print("="*80)
        
        response = input("\nProceed with fixes? (yes/no): ")
        if response.lower() == 'yes':
            fix_duplicate_transactions(all_issues)
            fix_lot_quantities(all_issues)
            print("\nFixes applied!")
        else:
            print("\nFixes skipped")
    else:
        print("\nNo issues found - inventory is clean!")
    
    print("="*80)

if __name__ == '__main__':
    main()
