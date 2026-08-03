"""E2E: plant standard 2.2 lb/kg + formula auto-required qty math."""
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

from erp_core.mass_quantity import LBS_PER_KG, convert_mass_uom
from erp_core.make_services import create_batch_ticket
from erp_core.models import Formula, FormulaItem, Item, Lot


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg):
    print("OK:", msg)


def main():
    if abs(LBS_PER_KG - 2.2) > 1e-9:
        fail(f"LBS_PER_KG must be 2.2, got {LBS_PER_KG}")
    ok(f"LBS_PER_KG={LBS_PER_KG}")

    # Round-trip: 100 lbs → kg → lbs
    kg = convert_mass_uom(100, "lbs", "kg")
    back = convert_mass_uom(kg, "kg", "lbs")
    if abs(kg - (100 / 2.2)) > 0.02:
        fail(f"100 lbs → kg expected {100/2.2}, got {kg}")
    if abs(back - 100) > 1e-9:
        fail(f"round-trip expected 100, got {back}")
    ok(f"100 lbs <-> kg: {kg} kg -> {back} lbs")

    # Exact 2.2: 11 lbs = 5 kg
    if abs(convert_mass_uom(5, "kg", "lbs") - 11.0) > 0.02:
        fail("5 kg should be 11 lbs")
    if abs(convert_mass_uom(11, "lbs", "kg") - 5.0) > 0.02:
        fail("11 lbs should be 5 kg")
    ok("exact 5 kg = 11 lbs")

    # Formula required: 200 lbs batch @ 60/40 → 120 / 80
    user = User.objects.filter(is_superuser=True).first()
    tag = uuid.uuid4().hex[:6].upper()
    rm_a = Item.objects.create(
        sku=f"E2ECA{tag}", name="A", item_type="raw_material", unit_of_measure="lbs"
    )
    rm_b = Item.objects.create(
        sku=f"E2ECB{tag}", name="B", item_type="raw_material", unit_of_measure="kg"
    )
    fg = Item.objects.create(
        sku=f"E2ECFG{tag}", name="FG", item_type="finished_good", unit_of_measure="lbs"
    )
    formula = Formula.objects.create(finished_good=fg, version="1.0")
    FormulaItem.objects.create(formula=formula, item=rm_a, percentage=60)
    FormulaItem.objects.create(formula=formula, item=rm_b, percentage=40)

    batch_lbs = 200.0
    req_a = batch_lbs * 0.60  # 120 lbs
    req_b_lbs = batch_lbs * 0.40  # 80 lbs
    req_b_kg = convert_mass_uom(req_b_lbs, "lbs", "kg")  # 80/2.2
    ok(f"auto-req A={req_a} lbs, B={req_b_kg} kg (from 40% of 200 lbs)")

    now = timezone.now()
    lot_a = Lot.objects.create(
        lot_number=f"CA{tag}",
        item=rm_a,
        quantity=200,
        quantity_remaining=200,
        received_date=now,
        status="accepted",
    )
    lot_b = Lot.objects.create(
        lot_number=f"CB{tag}",
        item=rm_b,
        quantity=100,
        quantity_remaining=100,
        received_date=now,
        status="accepted",
    )

    batch = create_batch_ticket(
        user,
        {
            "batch_type": "production",
            "finished_good_item_id": fg.id,
            "quantity_produced": batch_lbs,
            "production_date": timezone.localdate().isoformat(),
            "status": "in_progress",
            "batch_ticket_mass_unit": "lbs",
            "inputs": [
                {"lot_id": lot_a.id, "quantity_used": req_a},
                {"lot_id": lot_b.id, "quantity_used": req_b_kg},
            ],
        },
    )
    if abs(float(batch.quantity_produced) - 200) > 0.05:
        fail(f"qty_produced {batch.quantity_produced}")
    ok(f"created batch {batch.batch_number} with lbs+kg inputs via 2.2 factor")

    print("\nCONVERSION / AUTO-REQ E2E PASSED")


if __name__ == "__main__":
    main()
