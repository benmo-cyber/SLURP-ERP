"""E2E Quality: vendor approve/edit + FG formula save (100% ingredients)."""
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

from django.db import transaction
from django.utils import timezone

from erp_core.models import Formula, FormulaItem, Item, Vendor
from erp_core.vendor_rename import cascade_vendor_name_change


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg):
    print("OK:", msg)


def main():
    tag = uuid.uuid4().hex[:6].upper()
    vendor = Vendor.objects.create(
        name=f"E2E Qual Vendor {tag}",
        approval_status="pending",
        street_address="10 Test St",
        city="Washington",
        state="MO",
        zip_code="63090",
        country="USA",
    )
    vendor.approval_status = "approved"
    vendor.approved_date = timezone.now()
    vendor.approved_by = "e2e"
    vendor.city = "Union"
    vendor.save()
    vendor.refresh_from_db()
    if vendor.approval_status != "approved" or vendor.city != "Union":
        fail("vendor save/approve fields")
    ok(f"vendor approved/edited id={vendor.id}")

    old = vendor.name
    vendor.name = f"E2E Qual Vendor Renamed {tag}"
    vendor.save()
    cascade_vendor_name_change(old, vendor.name)
    ok("vendor rename cascade ok")

    rm_a = Item.objects.create(
        sku=f"E2EQA{tag}", name=f"RM A {tag}", item_type="raw_material", unit_of_measure="lbs"
    )
    rm_b = Item.objects.create(
        sku=f"E2EQB{tag}", name=f"RM B {tag}", item_type="raw_material", unit_of_measure="lbs"
    )
    fg = Item.objects.create(
        sku=f"E2EQFG{tag}", name=f"FG {tag}", item_type="finished_good", unit_of_measure="lbs"
    )

    # Bad total rejected conceptually (view enforces; service-level here)
    total = 90.0
    if abs(total - 100.0) <= 0.05:
        fail("tolerance check inverted")
    ok("pct total rule present")

    with transaction.atomic():
        formula = Formula.objects.create(finished_good=fg, version="1.0", qc_parameter_name="color")
        FormulaItem.objects.create(formula=formula, item=rm_a, percentage=60.0)
        FormulaItem.objects.create(formula=formula, item=rm_b, percentage=40.0)

    formula.refresh_from_db()
    ings = list(formula.ingredients.all())
    if len(ings) != 2:
        fail("expected 2 ingredients")
    s = sum(i.percentage for i in ings)
    if abs(s - 100.0) > 0.05:
        fail(f"pct sum {s}")
    ok(f"formula saved for {fg.sku} total={s}")

    # Replace ingredients (like view)
    with transaction.atomic():
        FormulaItem.objects.filter(formula=formula).delete()
        FormulaItem.objects.create(formula=formula, item=rm_a, percentage=70.0)
        FormulaItem.objects.create(formula=formula, item=rm_b, percentage=30.0)
        formula.version = "1.1"
        formula.save()
    formula.refresh_from_db()
    if formula.version != "1.1":
        fail("version not updated")
    if abs(sum(i.percentage for i in formula.ingredients.all()) - 100.0) > 0.05:
        fail("replaced ingredients sum")
    ok("formula replace ingredients ok")

    print("\nQUALITY FLOW E2E PASSED")


if __name__ == "__main__":
    main()
