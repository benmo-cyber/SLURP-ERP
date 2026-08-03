"""E2E Sell flow: Create SO → Issue → Allocate → Check Out (ship)."""
import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend_django"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone

from erp_core.models import Customer, Item, Lot, SalesOrder, ShipToLocation
from erp_core.sell_services import (
    SellFlowError,
    allocate_sales_order,
    create_sales_order,
    issue_sales_order,
    ship_sales_order,
)


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg):
    print("OK:", msg)


def main():
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        fail("No superuser in DB")

    tag = uuid.uuid4().hex[:6].upper()
    customer = Customer.objects.create(
        customer_id=f"E2E-C-{tag}",
        name=f"E2E Sell Customer {tag}",
        payment_terms="Net 30",
        is_active=True,
    )
    ship_to = ShipToLocation.objects.create(
        customer=customer,
        location_name="Main",
        address="1 Test Rd",
        city="Washington",
        state="MO",
        zip_code="63090",
        country="USA",
        is_default=True,
        is_active=True,
    )
    # Use raw_material (not gated FG) so allocate doesn't need closed batch outputs
    item = Item.objects.create(
        sku=f"E2ES{tag}",
        name=f"E2E sell item {tag}",
        item_type="raw_material",
        unit_of_measure="lbs",
    )
    lot = Lot.objects.create(
        lot_number=f"LS{tag}",
        vendor_lot_number=f"VL-{tag}",
        item=item,
        quantity=100.0,
        quantity_remaining=100.0,
        received_date=timezone.now(),
        status="accepted",
    )
    ok(f"customer={customer.name} item={item.sku} lot={lot.lot_number}")

    # Create
    so = create_sales_order(
        user,
        {
            "customer_id": customer.id,
            "ship_to_location": ship_to.id,
            "customer_reference_number": f"PO-{tag}",
            "status": "draft",
            "items": [
                {"item_id": item.id, "quantity_ordered": 40.0, "unit_price": 2.5},
            ],
        },
    )
    if so.status != "draft":
        fail(f"expected draft, got {so.status}")
    line = so.items.get()
    if abs(float(line.quantity_ordered) - 40.0) > 0.01:
        fail("line qty wrong")
    ok(f"created SO {so.so_number}")

    # Cannot ship without issue/allocate
    try:
        ship_sales_order(
            so,
            user,
            {
                "ship_date": timezone.localdate().isoformat(),
                "carrier": "Test",
                "pieces": 1,
                "piece_dimensions": ["12x12x12"],
                "piece_weights": ["40 lbs"],
                "items": [{"item_id": line.id, "quantity": 40}],
            },
        )
        fail("ship on draft should fail")
    except SellFlowError:
        ok("ship blocked on draft")

    # Issue
    so = issue_sales_order(so, user)
    if so.status != "issued":
        fail(f"expected issued, got {so.status}")
    ok("issued")

    # Allocate over available must fail
    try:
        allocate_sales_order(
            so,
            {
                "items": [
                    {
                        "item_id": item.id,
                        "allocations": [{"lot_id": lot.id, "quantity": 500}],
                    }
                ]
            },
        )
        fail("over-allocate should fail")
    except SellFlowError:
        ok("over-allocate blocked")

    # Allocate
    so = allocate_sales_order(
        so,
        {
            "items": [
                {
                    "item_id": item.id,
                    "allocations": [{"lot_id": lot.id, "quantity": 40.0}],
                }
            ]
        },
    )
    line.refresh_from_db()
    if abs(float(line.quantity_allocated) - 40.0) > 0.01:
        fail(f"alloc qty {line.quantity_allocated}")
    so.refresh_from_db()
    if so.status not in ("ready_for_shipment", "issued"):
        fail(f"unexpected status after alloc: {so.status}")
    # Lot not consumed until ship
    lot.refresh_from_db()
    if abs(float(lot.quantity_remaining) - 100.0) > 0.01:
        fail("lot should still be 100 after allocate")
    ok(f"allocated; status={so.status}")

    # Ship
    result = ship_sales_order(
        so,
        user,
        {
            "ship_date": timezone.localdate().isoformat(),
            "invoice_date": timezone.localdate().isoformat(),
            "carrier": "E2E Carrier",
            "tracking_number": f"TRK-{tag}",
            "pieces": 1,
            "piece_dimensions": ['48x40x36"'],
            "piece_weights": ["40 lbs"],
            "items": [{"item_id": line.id, "quantity": 40.0}],
        },
    )
    so.refresh_from_db()
    lot.refresh_from_db()
    line.refresh_from_db()
    if so.status != "completed":
        fail(f"expected completed, got {so.status}")
    if abs(float(lot.quantity_remaining) - 60.0) > 0.05:
        fail(f"lot remaining expected 60, got {lot.quantity_remaining}")
    if abs(float(line.quantity_shipped) - 40.0) > 0.05:
        fail(f"shipped qty {line.quantity_shipped}")
    inv = result.get("invoice") or {}
    if not inv.get("id") and not inv.get("invoice_number"):
        fail(f"missing invoice in result: {result.keys()}")
    ok(f"shipped; invoice={inv.get('invoice_number')}; lot remaining={lot.quantity_remaining}")

    # Drop-ship path
    so2 = create_sales_order(
        user,
        {
            "customer_id": customer.id,
            "ship_to_location": ship_to.id,
            "drop_ship": True,
            "status": "draft",
            "items": [
                {"item_id": item.id, "quantity_ordered": 5.0, "unit_price": 1.0},
            ],
        },
    )
    so2 = issue_sales_order(so2, user)
    so2 = allocate_sales_order(so2, {"items": []})
    if so2.status != "ready_for_shipment":
        fail(f"drop-ship expected ready_for_shipment, got {so2.status}")
    line2 = so2.items.get()
    before = float(Lot.objects.get(pk=lot.pk).quantity_remaining)
    ship_sales_order(
        so2,
        user,
        {
            "ship_date": timezone.localdate().isoformat(),
            "carrier": "DS Carrier",
            "pieces": 1,
            "piece_dimensions": ["1x1x1"],
            "piece_weights": ["5 lbs"],
            "items": [{"item_id": line2.id, "quantity": 5.0}],
        },
    )
    after = float(Lot.objects.get(pk=lot.pk).quantity_remaining)
    if abs(after - before) > 0.01:
        fail("drop-ship should not consume inventory")
    so2.refresh_from_db()
    if so2.status != "completed":
        fail(f"drop-ship expected completed, got {so2.status}")
    ok("drop-ship allocate+ship skips inventory")

    print("\nSELL FLOW E2E PASSED")


if __name__ == "__main__":
    main()
