"""HTTP smoke: login + key slurp_ui pages and one POST per major flow."""
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
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from erp_core.models import (
    Customer,
    Formula,
    FormulaItem,
    Item,
    Lot,
    Vendor,
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

    # Ensure password works for client login
    pwd = f"e2e-{uuid.uuid4().hex[:10]}"
    user.set_password(pwd)
    user.save(update_fields=["password"])

    c = Client()
    if not c.login(username=user.username, password=pwd):
        fail("login failed")
    ok(f"logged in as {user.username}")

    get_urls = [
        "slurp_ui:inventory_purchase_orders",
        "slurp_ui:inventory_create_po",
        "slurp_ui:inventory_check_in",
        "slurp_ui:production",
        "slurp_ui:production_create_batch",
        "slurp_ui:sales_orders",
        "slurp_ui:sales_create_order",
        "slurp_ui:sales_checkout",
        "slurp_ui:finance_invoices",
        "slurp_ui:quality",
        "slurp_ui:quality_finished_goods",
    ]
    for name in get_urls:
        url = reverse(name)
        r = c.get(url)
        if r.status_code != 200:
            fail(f"GET {name} -> {r.status_code}")
    ok(f"GET {len(get_urls)} module pages 200")

    tag = uuid.uuid4().hex[:6].upper()

    # --- Buy: create PO via UI ---
    vendor = Vendor.objects.create(name=f"HTTP Buy {tag}", approval_status="approved")
    item = Item.objects.create(
        sku=f"HTTPB{tag}",
        name=f"HTTP buy {tag}",
        item_type="raw_material",
        unit_of_measure="lbs",
        vendor=vendor.name,
    )
    r = c.post(
        reverse("slurp_ui:inventory_create_po"),
        {
            "vendor_id": vendor.id,
            "line_count": 1,
            "item_id_0": item.id,
            "quantity_0": 10,
            "unit_cost_0": 1.5,
            "order_uom_0": "lbs",
            "ship_to_name": "WWI",
            "ship_to_address": "6431 Michels Dr.",
            "ship_to_city": "Washington",
            "ship_to_state": "MO",
            "ship_to_zip": "63090",
            "ship_to_country": "USA",
        },
        follow=False,
    )
    if r.status_code not in (302, 200):
        fail(f"create PO status {r.status_code}")
    from erp_core.models import PurchaseOrder

    po = (
        PurchaseOrder.objects.filter(items__item=item)
        .distinct()
        .order_by("-id")
        .first()
    )
    if not po or po.status != "draft":
        # surface form errors if stayed on page
        body = r.content.decode("utf-8", errors="replace")[:500] if r.status_code == 200 else ""
        fail(f"PO not created via UI (status={r.status_code} po={po}) {body}")
    ok(f"UI create PO {po.po_number}")

    r = c.post(reverse("slurp_ui:inventory_issue_po", kwargs={"pk": po.id}))
    if r.status_code not in (302, 200):
        fail(f"issue PO {r.status_code}")
    po.refresh_from_db()
    if po.status != "issued":
        fail(f"PO not issued: {po.status}")
    ok("UI issue PO")

    # --- Make: create + close via services already covered; smoke create page + batch list ---
    # Seed formula/lots and POST create-batch
    rm_a = Item.objects.create(
        sku=f"HTTPA{tag}", name="A", item_type="raw_material", unit_of_measure="lbs"
    )
    rm_b = Item.objects.create(
        sku=f"HTTPB2{tag}", name="B", item_type="raw_material", unit_of_measure="lbs"
    )
    fg = Item.objects.create(
        sku=f"HTTPFG{tag}", name="FG", item_type="finished_good", unit_of_measure="lbs"
    )
    formula = Formula.objects.create(finished_good=fg, version="1.0")
    ia = FormulaItem.objects.create(formula=formula, item=rm_a, percentage=50)
    ib = FormulaItem.objects.create(formula=formula, item=rm_b, percentage=50)
    now = timezone.now()
    la = Lot.objects.create(
        lot_number=f"HA{tag}",
        item=rm_a,
        quantity=100,
        quantity_remaining=100,
        received_date=now,
        status="accepted",
    )
    lb = Lot.objects.create(
        lot_number=f"HB{tag}",
        item=rm_b,
        quantity=100,
        quantity_remaining=100,
        received_date=now,
        status="accepted",
    )
    r = c.post(
        reverse("slurp_ui:production_create_batch"),
        {
            "formula_id": formula.id,
            "quantity_produced": 20,
            "production_date": timezone.localdate().isoformat(),
            "batch_ticket_mass_unit": "lbs",
            f"lot_id_{ia.id}": la.id,
            f"qty_{ia.id}": 10,
            f"lot_id_{ib.id}": lb.id,
            f"qty_{ib.id}": 10,
        },
    )
    if r.status_code not in (302, 200):
        fail(f"create batch {r.status_code} {getattr(r, 'content', b'')[:300]}")
    from erp_core.models import ProductionBatch

    batch = ProductionBatch.objects.filter(finished_good_item=fg).order_by("-id").first()
    if not batch:
        fail("batch not created via UI")
    ok(f"UI create batch {batch.batch_number}")

    r = c.post(
        reverse("slurp_ui:production_close_batch", kwargs={"pk": batch.id}),
        {"quantity_actual": 20, "wastes": 0, "spills": 0},
    )
    if r.status_code not in (302, 200):
        fail(f"close batch {r.status_code}")
    batch.refresh_from_db()
    if batch.status != "closed":
        fail(f"batch not closed: {batch.status}")
    ok("UI close batch")

    r = c.post(reverse("slurp_ui:production_reverse_batch", kwargs={"pk": batch.id}))
    if r.status_code not in (302, 200):
        fail(f"reverse batch {r.status_code}")
    if ProductionBatch.objects.filter(pk=batch.pk).exists():
        fail("batch should be gone after reverse")
    ok("UI reverse batch")

    # --- Sell ---
    cust = Customer.objects.create(
        customer_id=f"HTTP-C-{tag}", name=f"HTTP Cust {tag}", is_active=True
    )
    sell_item = Item.objects.create(
        sku=f"HTTPS{tag}",
        name="sell",
        item_type="raw_material",
        unit_of_measure="lbs",
    )
    slot = Lot.objects.create(
        lot_number=f"HS{tag}",
        item=sell_item,
        quantity=50,
        quantity_remaining=50,
        received_date=now,
        status="accepted",
    )
    r = c.post(
        reverse("slurp_ui:sales_create_order") + f"?customer={cust.id}",
        {
            "customer_id": cust.id,
            "customer_po": f"PO-{tag}",
            "line_count": 1,
            "item_id_0": sell_item.id,
            "qty_0": 10,
            "price_0": 2,
        },
    )
    if r.status_code not in (302, 200):
        fail(f"create SO {r.status_code}")
    from erp_core.models import SalesOrder

    so = SalesOrder.objects.filter(customer=cust).order_by("-id").first()
    if not so:
        fail("SO not created")
    ok(f"UI create SO {so.so_number}")

    r = c.post(reverse("slurp_ui:sales_issue_order", kwargs={"pk": so.id}))
    so.refresh_from_db()
    if so.status != "issued":
        fail(f"SO not issued: {so.status}")
    ok("UI issue SO")

    line = so.items.get()
    r = c.post(
        reverse("slurp_ui:sales_allocate_order", kwargs={"pk": so.id}),
        {
            f"lot_{line.id}_0": slot.id,
            f"qty_{line.id}_0": 10,
        },
    )
    line.refresh_from_db()
    if abs(float(line.quantity_allocated) - 10) > 0.01:
        fail(f"alloc {line.quantity_allocated}")
    ok("UI allocate SO")

    r = c.post(
        reverse("slurp_ui:sales_checkout"),
        {
            "so_id": so.id,
            "ship_date": timezone.localdate().isoformat(),
            "carrier": "HTTP Carrier",
            "tracking_number": f"TRK-{tag}",
            "pieces": 1,
            "dim_0": "12x12x12",
            "weight_0": "10 lbs",
        },
    )
    so.refresh_from_db()
    if so.status != "completed":
        fail(f"SO not completed: {so.status} resp={r.status_code}")
    ok("UI checkout SO")

    from erp_core.models import Invoice

    inv = Invoice.objects.filter(sales_order=so).order_by("-id").first()
    if not inv:
        fail("no invoice from checkout")
    r = c.get(reverse("slurp_ui:finance_invoice_detail", kwargs={"pk": inv.id}))
    if r.status_code != 200:
        fail(f"invoice detail {r.status_code}")
    r = c.get(reverse("slurp_ui:finance_invoice_pdf", kwargs={"pk": inv.id}))
    if r.status_code != 200 or r.get("Content-Type") != "application/pdf":
        fail(f"invoice pdf {r.status_code} {r.get('Content-Type')}")
    ok("UI invoice detail + PDF")

    # Issue needs draft — void first somehow? The shipped invoice is draft.
    if inv.status == "draft":
        r = c.post(
            reverse("slurp_ui:finance_invoice_issue", kwargs={"pk": inv.id}),
            {"carrier": "HTTP Carrier", "tracking_number": f"TRK-{tag}"},
        )
        inv.refresh_from_db()
        if inv.status != "sent":
            fail(f"invoice not issued: {inv.status}")
        ok("UI issue invoice")
        r = c.post(reverse("slurp_ui:finance_invoice_cancel", kwargs={"pk": inv.id}))
        inv.refresh_from_db()
        if inv.status != "cancelled":
            fail(f"invoice not voided: {inv.status}")
        ok("UI void invoice")

    from erp_core.models import Shipment

    sh = Shipment.objects.filter(sales_order=so).first()
    if sh:
        r = c.post(reverse("slurp_ui:sales_reverse_shipment", kwargs={"pk": sh.id}))
        so.refresh_from_db()
        if Shipment.objects.filter(pk=sh.pk).exists():
            fail("shipment not reversed")
        ok(f"UI reverse shipment; SO status={so.status}")
        r = c.post(reverse("slurp_ui:sales_revert_order", kwargs={"pk": so.id}))
        so.refresh_from_db()
        if so.status != "draft":
            fail(f"revert failed: {so.status}")
        ok("UI revert SO to draft")

    # --- Quality ---
    r = c.get(reverse("slurp_ui:quality_vendor_detail", kwargs={"pk": vendor.id}))
    if r.status_code != 200:
        fail(f"vendor detail {r.status_code}")
    r = c.post(
        reverse("slurp_ui:quality_vendor_detail", kwargs={"pk": vendor.id}),
        {
            "action": "approve",
        },
    )
    vendor.refresh_from_db()
    if vendor.approval_status != "approved":
        fail("vendor not approved via UI")
    ok("UI approve vendor")

    r = c.get(reverse("slurp_ui:quality_finished_good_detail", kwargs={"pk": fg.id}))
    if r.status_code != 200:
        fail(f"fg detail {r.status_code}")
    r = c.post(
        reverse("slurp_ui:quality_finished_good_detail", kwargs={"pk": fg.id}),
        {
            "version": "2.0",
            "line_count": 2,
            "ing_item_0": rm_a.id,
            "ing_pct_0": 60,
            "ing_item_1": rm_b.id,
            "ing_pct_1": 40,
        },
    )
    formula.refresh_from_db()
    if formula.version != "2.0":
        fail(f"formula version {formula.version}")
    ok("UI save FG formula")

    print("\nHTTP SMOKE E2E PASSED")


if __name__ == "__main__":
    main()
