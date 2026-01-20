"""
Find if there are missing lots or if lot quantities are wrong
Check purchase orders and receipts for D1300K0010
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import Lot, Item, PurchaseOrder, PurchaseOrderItem, InventoryTransaction
from django.db import connection

item = Item.objects.get(sku='D1300K0010')
print(f"Item: {item.name} ({item.sku})")
print("="*80)

# Check purchase orders
print("\nPURCHASE ORDERS FOR D1300K0010:")
pos = PurchaseOrderItem.objects.filter(item=item).select_related('purchase_order')
total_ordered = 0.0
total_received = 0.0

for po_item in pos:
    po = po_item.purchase_order
    print(f"  PO: {po.po_number} | Status: {po.status}")
    print(f"    Ordered: {po_item.quantity_ordered} | Received: {po_item.quantity_received}")
    total_ordered += po_item.quantity_ordered
    total_received += po_item.quantity_received

print(f"\n  TOTAL ORDERED: {total_ordered}")
print(f"  TOTAL RECEIVED (per PO): {total_received}")

# Check all receipt transactions
print("\nALL RECEIPT TRANSACTIONS:")
receipts = InventoryTransaction.objects.filter(
    lot__item=item,
    transaction_type='receipt'
).order_by('transaction_date')

total_receipts = 0.0
for receipt in receipts:
    print(f"  {receipt.transaction_date} | Lot: {receipt.lot.lot_number} | Qty: {receipt.quantity}")
    total_receipts += receipt.quantity

print(f"\n  TOTAL FROM RECEIPTS: {total_receipts}")

# Check all lots
print("\nALL LOTS:")
lots = Lot.objects.filter(item=item).order_by('received_date')
total_lot_quantity = 0.0
for lot in lots:
    print(f"  Lot: {lot.lot_number} | Status: {lot.status}")
    print(f"    Quantity: {lot.quantity} | Remaining: {lot.quantity_remaining}")
    total_lot_quantity += lot.quantity

print(f"\n  TOTAL LOT QUANTITIES: {total_lot_quantity}")

# Summary
print("\n" + "="*80)
print("SUMMARY:")
print(f"  Total Ordered (POs): {total_ordered}")
print(f"  Total Received (POs): {total_received}")
print(f"  Total Receipt Transactions: {total_receipts}")
print(f"  Total Lot Quantities: {total_lot_quantity}")
print(f"  User says total received: 10560")
print("="*80)
