"""E2E: Sell ship → reverse shipment → re-allocate → revert to draft."""
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

from erp_core.invoice_services import cancel_invoice, issue_invoice
from erp_core.models import Customer, Invoice, Item, Lot, SalesOrder, ShipToLocation, Shipment
from erp_core.sell_services import (
    SellFlowError,
    allocate_sales_order,
    create_sales_order,
    issue_sales_order,
    revert_sales_order_to_draft,
    reverse_sales_shipment,
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
        fail("No superuser")

    tag = uuid.uuid4().hex[:6].upper()
    customer = Customer.objects.create(
        customer_id=f"E2E-RV-{tag}",
        name=f"E2E Reverse {tag}",
        payment_terms="Net 30",
        is_active=True,
    )
    ship_to = ShipToLocation.objects.create(
        customer=customer,
        location_name="Main",
        address="1 Test",
        city="Washington",
        state="MO",
        zip_code="63090",
        country="USA",
        is_default=True,
        is_active=True,
    )
    item = Item.objects.create(
        sku=f"E2ERV{tag}",
        name=f"E2E reverse item {tag}",
        item_type="raw_material",
        unit_of_measure="lbs",
    )
    lot = Lot.objects.create(
        lot_number=f"LR{tag}",
        vendor_lot_number=f"VL-{tag}",
        item=item,
        quantity=80.0,
        quantity_remaining=80.0,
        received_date=timezone.now(),
        status="accepted",
    )

    so = create_sales_order(
        user,
        {
            "customer_id": customer.id,
            "ship_to_location": ship_to.id,
            "status": "draft",
            "items": [{"item_id": item.id, "quantity_ordered": 25.0, "unit_price": 3.0}],
        },
    )
    so = issue_sales_order(so, user)
    so = allocate_sales_order(
        so,
        {"items": [{"item_id": item.id, "allocations": [{"lot_id": lot.id, "quantity": 25.0}]}]},
    )
    line = so.items.get()
    result = ship_sales_order(
        so,
        user,
        {
            "ship_date": timezone.localdate().isoformat(),
            "carrier": "E2E",
            "tracking_number": f"TRK-{tag}",
            "pieces": 1,
            "piece_dimensions": ["12x12x12"],
            "piece_weights": ["25 lbs"],
            "items": [{"item_id": line.id, "quantity": 25.0}],
        },
    )
    so.refresh_from_db()
    lot.refresh_from_db()
    if so.status != "completed":
        fail(f"expected completed, got {so.status}")
    if abs(float(lot.quantity_remaining) - 55.0) > 0.05:
        fail(f"lot after ship expected 55, got {lot.quantity_remaining}")
    shipment_id = (result.get("shipment") or {}).get("id")
    if not shipment_id:
        # fallback: find latest shipment
        sh = Shipment.objects.filter(sales_order=so).order_by("-id").first()
        if not sh:
            fail("no shipment in result")
        shipment_id = sh.id
    inv_id = (result.get("invoice") or {}).get("id")
    ok(f"shipped shipment={shipment_id} inv={inv_id}; lot={lot.quantity_remaining}")

    # Issued invoice blocks reverse
    inv = Invoice.objects.get(pk=inv_id)
    issue_invoice(inv, carrier="E2E", tracking_number=f"TRK-{tag}", send_email=False)
    try:
        reverse_sales_shipment(shipment_id, user)
        fail("reverse with issued invoice should fail")
    except SellFlowError:
        ok("reverse blocked while invoice issued")
    cancel_invoice(inv)
    ok("voided invoice")

    info = reverse_sales_shipment(shipment_id, user)
    so.refresh_from_db()
    lot.refresh_from_db()
    line.refresh_from_db()
    if Shipment.objects.filter(pk=shipment_id).exists():
        fail("shipment should be deleted")
    if abs(float(lot.quantity_remaining) - 80.0) > 0.05:
        fail(f"lot restored expected 80, got {lot.quantity_remaining}")
    if abs(float(line.quantity_shipped) - 0.0) > 0.05:
        fail(f"shipped qty expected 0, got {line.quantity_shipped}")
    if so.status not in ("ready_for_shipment", "issued"):
        fail(f"unexpected status after reverse: {so.status}")
    ok(f"reversed; status={so.status}; lot={lot.quantity_remaining}")

    # Revert to draft
    so = revert_sales_order_to_draft(so, user)
    if so.status != "draft":
        fail(f"expected draft, got {so.status}")
    line.refresh_from_db()
    if float(line.quantity_allocated or 0) > 0.01:
        fail("allocations should be released")
    ok("reverted to draft; allocations cleared")

    # Non-staff blocked
    peon = User.objects.filter(is_staff=False, is_superuser=False).first()
    if peon is None:
        peon = User.objects.create_user(username=f"e2epeon{tag}", password="x")
    so2 = create_sales_order(
        user,
        {
            "customer_id": customer.id,
            "status": "draft",
            "items": [{"item_id": item.id, "quantity_ordered": 1.0, "unit_price": 1.0}],
        },
    )
    so2 = issue_sales_order(so2, user)
    try:
        revert_sales_order_to_draft(so2, peon)
        fail("non-staff revert should fail")
    except SellFlowError as e:
        if e.status_code != 403:
            fail(f"expected 403, got {e.status_code}")
        ok("non-staff revert forbidden")

    print("\nREVERSE / REVERT E2E PASSED")


if __name__ == "__main__":
    main()
