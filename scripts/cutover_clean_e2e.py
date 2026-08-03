"""
Cutover helper: delete E2E / HTTP-smoke test rows from the shared SQLite DB.
Keeps real plant masters and transactions. Requires a DB backup first.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")

import django

django.setup()

from django.db import transaction
from django.db.models import Q

from erp_core.models import (
    AccountsPayable,
    AccountsReceivable,
    Customer,
    CustomerContact,
    CustomerPricing,
    Formula,
    FormulaItem,
    Invoice,
    InvoiceItem,
    Item,
    ItemPackSize,
    Lot,
    LotCoaCertificate,
    LotTransactionLog,
    ProductionBatch,
    ProductionBatchInput,
    ProductionBatchOutput,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    SalesOrderLot,
    Shipment,
    ShipToLocation,
    Vendor,
    VendorContact,
)


def _e2e_items():
    return Item.objects.filter(
        Q(sku__istartswith="E2E")
        | Q(sku__istartswith="HTTP")
        | Q(name__icontains="E2E")
        | Q(vendor__iexact="E2E")
    )


def _e2e_customers():
    return Customer.objects.filter(
        Q(customer_id__istartswith="E2E")
        | Q(name__icontains="E2E")
        | Q(customer_id__istartswith="HTTP")
    )


def _e2e_vendors():
    return Vendor.objects.filter(Q(name__icontains="E2E") | Q(vendor_id__icontains="E2E"))


def main() -> int:
    items = list(_e2e_items())
    item_ids = [i.id for i in items]
    customers = list(_e2e_customers())
    customer_ids = [c.id for c in customers]
    vendors = list(_e2e_vendors())
    vendor_ids = [v.id for v in vendors]

    lots = list(
        Lot.objects.filter(
            Q(item_id__in=item_ids)
            | Q(lot_number__icontains="E2E")
            | Q(vendor_lot_number__icontains="E2E")
        )
    )
    lot_ids = [lot.id for lot in lots]

    sos = list(
        SalesOrder.objects.filter(
            Q(customer_id__in=customer_ids)
            | Q(customer_name__icontains="E2E")
            | Q(notes__icontains="E2E")
            | Q(items__item_id__in=item_ids)
        ).distinct()
    )
    so_ids = [so.id for so in sos]

    pos = list(
        PurchaseOrder.objects.filter(
            Q(vendor_customer_name__icontains="E2E")
            | Q(notes__icontains="E2E")
            | Q(items__item_id__in=item_ids)
        ).distinct()
    )
    po_ids = [po.id for po in pos]

    invoices = list(
        Invoice.objects.filter(
            Q(sales_order_id__in=so_ids)
            | Q(customer_vendor_name__icontains="E2E")
            | Q(notes__icontains="E2E")
            | Q(items__item_id__in=item_ids)
        ).distinct()
    )
    inv_ids = [inv.id for inv in invoices]

    batches = list(
        ProductionBatch.objects.filter(
            Q(finished_good_item_id__in=item_ids)
            | Q(notes__icontains="E2E")
            | Q(inputs__lot_id__in=lot_ids)
            | Q(outputs__lot_id__in=lot_ids)
        ).distinct()
    )
    batch_ids = [b.id for b in batches]

    print("Will delete:")
    print(f"  items={len(item_ids)} customers={len(customer_ids)} vendors={len(vendor_ids)}")
    print(f"  lots={len(lot_ids)} SOs={len(so_ids)} POs={len(po_ids)} invoices={len(inv_ids)} batches={len(batch_ids)}")

    with transaction.atomic():
        # Downstream docs / allocations first
        Shipment.objects.filter(sales_order_id__in=so_ids).delete()
        SalesOrderLot.objects.filter(
            Q(lot_id__in=lot_ids) | Q(sales_order_item__sales_order_id__in=so_ids)
        ).delete()
        InvoiceItem.objects.filter(invoice_id__in=inv_ids).delete()
        AccountsReceivable.objects.filter(invoice_id__in=inv_ids).delete()
        Invoice.objects.filter(id__in=inv_ids).delete()

        ProductionBatchInput.objects.filter(batch_id__in=batch_ids).delete()
        ProductionBatchOutput.objects.filter(batch_id__in=batch_ids).delete()
        ProductionBatch.objects.filter(id__in=batch_ids).delete()

        SalesOrderItem.objects.filter(sales_order_id__in=so_ids).delete()
        SalesOrder.objects.filter(id__in=so_ids).delete()

        PurchaseOrderItem.objects.filter(purchase_order_id__in=po_ids).delete()
        AccountsPayable.objects.filter(purchase_order_id__in=po_ids).delete()
        PurchaseOrder.objects.filter(id__in=po_ids).delete()

        LotCoaCertificate.objects.filter(lot_id__in=lot_ids).delete()
        LotTransactionLog.objects.filter(lot_id__in=lot_ids).delete()
        Lot.objects.filter(id__in=lot_ids).delete()

        FormulaItem.objects.filter(formula__finished_good_id__in=item_ids).delete()
        Formula.objects.filter(finished_good_id__in=item_ids).delete()
        ItemPackSize.objects.filter(item_id__in=item_ids).delete()
        CustomerPricing.objects.filter(
            Q(customer_id__in=customer_ids) | Q(item_id__in=item_ids)
        ).delete()

        Item.objects.filter(id__in=item_ids).delete()

        CustomerContact.objects.filter(customer_id__in=customer_ids).delete()
        ShipToLocation.objects.filter(customer_id__in=customer_ids).delete()
        SalesCall.objects.filter(customer_id__in=customer_ids).delete()
        Customer.objects.filter(id__in=customer_ids).delete()

        VendorContact.objects.filter(vendor_id__in=vendor_ids).delete()
        Vendor.objects.filter(id__in=vendor_ids).delete()

    # Verify
    left_items = _e2e_items().count()
    left_cust = _e2e_customers().count()
    left_lots = Lot.objects.filter(lot_number__icontains="E2E").count()
    print(f"Remaining E2E items={left_items} customers={left_cust} lots={left_lots}")
    print(f"Remaining plant Items={Item.objects.count()} Customers={Customer.objects.count()} Lots={Lot.objects.count()}")
    if left_items or left_cust or left_lots:
        print("WARN: some E2E rows remain")
        return 1
    print("CUTOVER CLEAN E2E PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
