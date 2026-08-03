"""E2E Buy flow: Create PO → Issue → Check-In → Reverse check-in."""
import os
import sys
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")
django.setup()

from django.contrib.auth.models import User

from erp_core.buy_services import (
    BuyFlowError,
    check_in_lot,
    create_purchase_order,
    issue_purchase_order,
    reverse_check_in,
)
from erp_core.models import Item, Lot, PurchaseOrder, PurchaseOrderItem, Vendor


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg):
    print("OK:", msg)


def main():
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        fail("No superuser in DB")

    vendor, _ = Vendor.objects.get_or_create(
        name=f"E2E Buy Vendor {uuid.uuid4().hex[:6]}",
        defaults={"approval_status": "approved", "country": "USA"},
    )
    sku = f"E2E{uuid.uuid4().hex[:6].upper()}"
    item = Item.objects.create(
        sku=sku,
        name=f"E2E raw {sku}",
        item_type="raw_material",
        unit_of_measure="lbs",
        vendor=vendor.name,
    )
    ok(f"vendor={vendor.name} item={item.sku}")

    # Create
    po = create_purchase_order(
        user,
        {
            "vendor_id": vendor.id,
            "status": "draft",
            "po_type": "vendor",
            "items": [
                {"item_id": item.id, "quantity": 100.0, "unit_cost": 1.25, "order_uom": "lbs"}
            ],
        },
    )
    if po.status != "draft":
        fail(f"expected draft, got {po.status}")
    line = po.items.get()
    if float(line.quantity_ordered) != 100.0:
        fail("line qty wrong")
    ok(f"created PO {po.po_number}")

    # Issue
    on_order_before = float(Item.objects.get(pk=item.pk).on_order or 0)
    po = issue_purchase_order(po, user)
    if po.status != "issued":
        fail(f"expected issued, got {po.status}")
    on_order_after = float(Item.objects.get(pk=item.pk).on_order or 0)
    if abs(on_order_after - on_order_before - 100.0) > 0.01:
        fail(f"on_order not +100 ({on_order_before} → {on_order_after})")
    ok("issued PO; on_order incremented")

    # Attestation required
    try:
        check_in_lot(
            user,
            {
                "item_id": item.id,
                "quantity": 40,
                "po_number": po.po_number,
                "vendor_lot_number": "VL-1",
                "status": "accepted",
            },
        )
        fail("check-in without attestations should fail")
    except BuyFlowError:
        ok("attestations enforced")

    # Check-in partial
    lot = check_in_lot(
        user,
        {
            "item_id": item.id,
            "quantity": 40,
            "po_number": po.po_number,
            "vendor_lot_number": "VL-E2E-1",
            "status": "accepted",
            "coa": True,
            "prod_free_pests": True,
            "carrier_free_pests": True,
            "shipment_accepted": True,
            "initials": "E2",
        },
    )
    po.refresh_from_db()
    line = PurchaseOrderItem.objects.get(pk=line.pk)
    if abs(float(line.quantity_received) - 40.0) > 0.01:
        fail(f"received qty {line.quantity_received}")
    if po.status != "issued":
        fail(f"partial should leave issued, got {po.status}")
    ok(f"partial check-in lot={lot.lot_number}")

    # Over-receipt blocked
    try:
        check_in_lot(
            user,
            {
                "item_id": item.id,
                "quantity": 100,
                "po_number": po.po_number,
                "vendor_lot_number": "VL-E2E-2",
                "status": "accepted",
                "coa": True,
                "prod_free_pests": True,
                "carrier_free_pests": True,
                "shipment_accepted": True,
                "initials": "E2",
            },
        )
        fail("over-receipt should fail")
    except BuyFlowError:
        ok("over-receipt blocked")

    # Complete check-in
    lot2 = check_in_lot(
        user,
        {
            "item_id": item.id,
            "quantity": 60,
            "entry_uom": "lbs",
            "po_number": po.po_number,
            "vendor_lot_number": "VL-E2E-3",
            "status": "accepted",
            "coa": True,
            "prod_free_pests": True,
            "carrier_free_pests": True,
            "shipment_accepted": True,
            "initials": "E2",
        },
    )
    po.refresh_from_db()
    if po.status != "received":
        fail(f"expected received after full check-in, got {po.status}")
    ok(f"full check-in lot2={lot2.lot_number}; PO received")

    # Reverse latest unused lot
    info = reverse_check_in(Lot.objects.get(pk=lot2.pk))
    po.refresh_from_db()
    line = PurchaseOrderItem.objects.get(pk=line.pk)
    if abs(float(line.quantity_received) - 40.0) > 0.01:
        fail(f"after reverse expected 40 received, got {line.quantity_received}")
    if Lot.objects.filter(pk=lot2.pk).exists():
        fail("lot2 should be deleted")
    ok(f"reversed {info.get('lot_number')}; PO qty rolled back")

    # kg conversion into lbs item
    lot3 = check_in_lot(
        user,
        {
            "item_id": item.id,
            "quantity": 10,  # kg
            "entry_uom": "kg",
            "po_number": po.po_number,
            "vendor_lot_number": "VL-E2E-KG",
            "status": "accepted",
            "coa": True,
            "prod_free_pests": True,
            "carrier_free_pests": True,
            "shipment_accepted": True,
            "initials": "E2",
        },
    )
    expected_lbs = 10 * 2.2
    if abs(float(lot3.quantity) - expected_lbs) > 0.05:
        fail(f"kg→lbs expected ~{expected_lbs}, got {lot3.quantity}")
    ok(f"kg entry converted to {lot3.quantity} lbs")

    print("\nBUY FLOW E2E PASSED")


if __name__ == "__main__":
    main()
