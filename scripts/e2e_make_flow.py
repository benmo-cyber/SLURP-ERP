"""E2E Make flow (production): Create batch → Close → Reverse."""
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

from erp_core.make_services import (
    MakeFlowError,
    close_batch_ticket,
    create_batch_ticket,
    reverse_batch_ticket,
)
from erp_core.models import Formula, FormulaItem, Item, Lot, ProductionBatch


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
    rm_a = Item.objects.create(
        sku=f"E2EMA{tag}",
        name=f"E2E RM A {tag}",
        item_type="raw_material",
        unit_of_measure="lbs",
    )
    rm_b = Item.objects.create(
        sku=f"E2EMB{tag}",
        name=f"E2E RM B {tag}",
        item_type="raw_material",
        unit_of_measure="lbs",
    )
    fg = Item.objects.create(
        sku=f"E2EMFG{tag}",
        name=f"E2E FG {tag}",
        item_type="finished_good",
        unit_of_measure="lbs",
    )
    formula = Formula.objects.create(finished_good=fg, version="1.0")
    FormulaItem.objects.create(formula=formula, item=rm_a, percentage=60.0)
    FormulaItem.objects.create(formula=formula, item=rm_b, percentage=40.0)

    now = timezone.now()
    lot_a = Lot.objects.create(
        lot_number=f"LA{tag}",
        vendor_lot_number=f"VL-A-{tag}",
        item=rm_a,
        quantity=200.0,
        quantity_remaining=200.0,
        received_date=now,
        status="accepted",
    )
    lot_b = Lot.objects.create(
        lot_number=f"LB{tag}",
        vendor_lot_number=f"VL-B-{tag}",
        item=rm_b,
        quantity=200.0,
        quantity_remaining=200.0,
        received_date=now,
        status="accepted",
    )
    ok(f"setup FG={fg.sku} lots={lot_a.lot_number},{lot_b.lot_number}")

    # Quantity mismatch must fail
    try:
        create_batch_ticket(
            user,
            {
                "batch_type": "production",
                "finished_good_item_id": fg.id,
                "quantity_produced": 100.0,
                "production_date": timezone.localdate().isoformat(),
                "status": "in_progress",
                "inputs": [
                    {"lot_id": lot_a.id, "quantity_used": 60.0},
                    {"lot_id": lot_b.id, "quantity_used": 30.0},  # short by 10
                ],
            },
        )
        fail("qty mismatch should fail")
    except MakeFlowError:
        ok("qty mismatch enforced")

    # Create
    batch = create_batch_ticket(
        user,
        {
            "batch_type": "production",
            "finished_good_item_id": fg.id,
            "quantity_produced": 100.0,
            "production_date": timezone.localdate().isoformat(),
            "status": "in_progress",
            "batch_ticket_mass_unit": "lbs",
            "notes": "e2e make",
            "inputs": [
                {"lot_id": lot_a.id, "quantity_used": 60.0},
                {"lot_id": lot_b.id, "quantity_used": 40.0},
            ],
        },
    )
    if batch.status == "closed":
        fail("create should leave open")
    if abs(float(batch.quantity_produced) - 100.0) > 0.02:
        fail(f"qty_produced {batch.quantity_produced}")
    if batch.inputs.count() != 2:
        fail("expected 2 inputs")
    # Inputs reserved, not consumed on create
    lot_a.refresh_from_db()
    lot_b.refresh_from_db()
    if abs(float(lot_a.quantity_remaining) - 200.0) > 0.01:
        fail("lot A should still be 200 after create")
    ok(f"created batch {batch.batch_number}")

    # Close with shortfall unexplained must fail
    try:
        close_batch_ticket(
            batch,
            user,
            {
                "status": "closed",
                "quantity_actual": 90.0,
                "wastes": 0,
                "spills": 0,
            },
        )
        fail("unexplained shortfall should fail")
    except MakeFlowError:
        ok("shortfall waste/spill rule enforced")
        batch.refresh_from_db()
        if batch.status == "closed":
            fail("batch should still be open after failed close")

    # Close success (actual = target)
    batch = close_batch_ticket(
        batch,
        user,
        {
            "status": "closed",
            "quantity_actual": 100.0,
            "wastes": 0,
            "spills": 0,
            "notes": "e2e closed",
        },
    )
    if batch.status != "closed":
        fail(f"expected closed, got {batch.status}")
    if not batch.outputs.exists():
        fail("expected output lot")
    out = batch.outputs.select_related("lot").first()
    if abs(float(out.quantity_produced) - 100.0) > 0.02:
        fail(f"output qty {out.quantity_produced}")
    if out.lot.status != "on_hold":
        fail(f"FG output should be on_hold, got {out.lot.status}")
    lot_a.refresh_from_db()
    lot_b.refresh_from_db()
    if abs(float(lot_a.quantity_remaining) - 140.0) > 0.05:
        fail(f"lot A after close expected 140, got {lot_a.quantity_remaining}")
    if abs(float(lot_b.quantity_remaining) - 160.0) > 0.05:
        fail(f"lot B after close expected 160, got {lot_b.quantity_remaining}")
    ok(f"closed; output lot={out.lot.lot_number} on_hold; inputs consumed")

    out_lot_id = out.lot_id

    # Reverse
    info = reverse_batch_ticket(batch)
    if ProductionBatch.objects.filter(pk=batch.pk).exists():
        fail("batch should be deleted after reverse")
    if Lot.objects.filter(pk=out_lot_id).exists():
        fail("output lot should be deleted after reverse")
    lot_a.refresh_from_db()
    lot_b.refresh_from_db()
    if abs(float(lot_a.quantity_remaining) - 200.0) > 0.05:
        fail(f"lot A after reverse expected 200, got {lot_a.quantity_remaining}")
    if abs(float(lot_b.quantity_remaining) - 200.0) > 0.05:
        fail(f"lot B after reverse expected 200, got {lot_b.quantity_remaining}")
    ok(f"reversed {info.get('batch_number')}; inputs restored; output removed")

    print("\nMAKE FLOW E2E PASSED")


if __name__ == "__main__":
    main()
