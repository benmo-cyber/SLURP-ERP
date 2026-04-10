"""
Single source of truth for lot quantity math in API responses.

Invariant (mass UoM, in-progress production does not reduce DB quantity_remaining):
  quantity_remaining_after_sales ≈ available + quantity_on_hold + committed_to_production
  (after normalizing commitments with the SAME values used in subtraction.)

Previously: committed was shown normalized (3150) but available used raw SUM (3149.96…), breaking balance.
"""
from __future__ import annotations

from django.db.models import Sum

from .mass_quantity import normalize_aggregate_quantity_by_uom, normalize_quantity_by_uom


def compute_lot_quantity_breakdown(lot):
    """
    Returns a dict of display-safe quantities that balance.

    Uses normalized aggregate amounts for sales / hold / production commitments in BOTH
    display fields AND the subtraction chain for available.
    """
    from .models import ProductionBatchInput, SalesOrderLot

    uom = getattr(lot.item, "unit_of_measure", None) if getattr(lot, "item_id", None) else "lbs"

    physical_raw = float(lot.quantity_remaining or 0)
    qty_received_raw = float(lot.quantity or 0)

    sales_raw = 0.0
    try:
        sales_raw = float(
            SalesOrderLot.objects.filter(
                lot=lot,
                sales_order_item__sales_order__status__in=[
                    "draft",
                    "allocated",
                    "issued",
                    "ready_for_shipment",
                ],
            ).aggregate(total=Sum("quantity_allocated"))["total"]
            or 0.0
        )
    except Exception:
        pass

    hold_raw = float(getattr(lot, "quantity_on_hold", 0) or 0)

    prod_raw = 0.0
    try:
        prod_raw = float(
            ProductionBatchInput.objects.filter(lot=lot, batch__status="in_progress").aggregate(
                total=Sum("quantity_used")
            )["total"]
            or 0.0
        )
    except Exception:
        pass

    # Normalized commitments (same numbers shown in UI and used in arithmetic)
    sales_n = normalize_aggregate_quantity_by_uom(sales_raw, uom)
    hold_n = normalize_aggregate_quantity_by_uom(hold_raw, uom)
    prod_n = normalize_aggregate_quantity_by_uom(prod_raw, uom)

    physical_n = normalize_quantity_by_uom(physical_raw, uom)
    qty_received_n = normalize_quantity_by_uom(qty_received_raw, uom)

    net_after_sales = max(0.0, physical_n - sales_n)
    net_after_sales = normalize_aggregate_quantity_by_uom(net_after_sales, uom)

    available = max(0.0, net_after_sales - hold_n - prod_n)
    available = normalize_aggregate_quantity_by_uom(available, uom)

    return {
        "unit_of_measure": uom,
        "quantity_received": qty_received_n,
        "quantity_physical": physical_n,
        "allocated_to_sales": sales_n,
        "quantity_on_hold": hold_n,
        "committed_to_production": prod_n,
        "quantity_remaining_after_sales": net_after_sales,
        "quantity_available_for_use": available,
    }
