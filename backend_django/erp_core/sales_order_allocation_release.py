"""
Release SalesOrderLot allocations and reverse distributed lots created for an SO.

Used when cancelling an order or reverting an issued order to draft.
"""
from __future__ import annotations

from .models import InventoryTransaction, SalesOrderLot


def release_sales_order_allocations(sales_order) -> None:
    """
    Delete all SalesOrderLot rows for this order, reverse distributed-item lots and raw
    material consumption where applicable, and zero quantity_allocated on each line.
    Does not change sales_order.status.
    """
    for so_item in sales_order.items.all():
        allocations = SalesOrderLot.objects.filter(sales_order_item=so_item)

        for allocation in allocations:
            lot = allocation.lot

            is_distributed_lot = InventoryTransaction.objects.filter(
                lot=lot,
                reference_number=sales_order.so_number,
                notes__icontains='distributed',
            ).exists()

            if is_distributed_lot:
                raw_material_transactions = InventoryTransaction.objects.filter(
                    reference_number=sales_order.so_number,
                    quantity__lt=0,
                    notes__icontains=lot.lot_number,
                )

                for trans in raw_material_transactions:
                    raw_lot = trans.lot
                    raw_lot.quantity_remaining += abs(trans.quantity)
                    raw_lot.save()

                    InventoryTransaction.objects.create(
                        transaction_type='adjustment',
                        lot=raw_lot,
                        quantity=abs(trans.quantity),
                        reference_number=sales_order.so_number,
                        notes=f'Reversed allocation from order {sales_order.so_number}',
                    )

                lot.delete()

        allocations.delete()
        so_item.quantity_allocated = 0.0
        so_item.save()
