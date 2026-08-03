"""E2E: lot hold → release (no COA) → reconcile path smoke for lot_services + inventory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend_django"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wwi_erp.settings")

import django

django.setup()

from django.contrib.auth import get_user_model

from django.utils import timezone

from erp_core.lot_display_quantities import compute_lot_quantity_breakdown
from erp_core.lot_services import LotFlowError, put_on_hold, reconcile_lot, release_from_hold
from erp_core.models import Item, Lot


def main() -> int:
    User = get_user_model()
    user = User.objects.filter(is_staff=True).first() or User.objects.first()
    if not user:
        print("FAIL: no user")
        return 1

    item = Item.objects.filter(item_type="raw_material").first()
    if not item:
        item = Item.objects.create(
            sku="E2E-HOLD-RM",
            name="E2E Hold RM",
            item_type="raw_material",
            unit_of_measure="lbs",
            vendor="E2E",
        )

    lot = Lot.objects.create(
        item=item,
        lot_number="E2E-HOLD-LOT",
        quantity=100.0,
        quantity_remaining=100.0,
        status="accepted",
        quantity_on_hold=0.0,
        on_hold=False,
        received_date=timezone.now(),
    )
    print(f"created lot {lot.id}")

    put_on_hold(lot, 25.0)
    lot.refresh_from_db()
    assert float(lot.quantity_on_hold) == 25.0, lot.quantity_on_hold
    avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
    assert avail <= 75.01, avail
    print("hold ok")

    release_from_hold(user, lot, 10.0, coa_payload=None)
    lot.refresh_from_db()
    assert float(lot.quantity_on_hold) == 15.0, lot.quantity_on_hold
    print("partial release ok")

    release_from_hold(user, lot, 15.0, coa_payload=None)
    lot.refresh_from_db()
    assert float(lot.quantity_on_hold) == 0.0
    assert lot.on_hold is False
    print("full release ok")

    reconcile_lot(user, lot, 90.0, reason="E2E reconcile")
    lot.refresh_from_db()
    assert float(lot.quantity_remaining) == 90.0
    print("reconcile ok")

    try:
        put_on_hold(lot, 9999.0)
        print("FAIL: should reject over-hold")
        return 1
    except LotFlowError:
        print("over-hold rejected ok")

    print("PASS e2e_lot_hold_flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
