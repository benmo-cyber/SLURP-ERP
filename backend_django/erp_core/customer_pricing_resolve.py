"""Resolve customer list prices into the item's native UoM for SO / invoice lines."""
from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone

from .mass_quantity import convert_unit_price


def unit_price_in_item_uom(
    unit_price: float | int | None,
    price_uom: str | None,
    item: Any,
) -> float:
    """
    Convert a quoted unit price into the item master UoM.

    Sales order qty and invoice qty are always in item.unit_of_measure; the
    unit_price on those lines must match. CustomerPricing may be stored in lbs
    while the pack SKU is kg (or the reverse).
    """
    if unit_price is None:
        return 0.0
    item_uom = (getattr(item, "unit_of_measure", None) or "lbs").strip() or "lbs"
    price_uom = (price_uom or item_uom).strip() or item_uom
    try:
        return float(convert_unit_price(unit_price, price_uom, item_uom))
    except ValueError:
        # Non-mass / unsupported — leave as entered (caller may surface error).
        return float(unit_price)


def customer_pricing_unit_price_for_item(cp, item=None) -> float:
    """Active CustomerPricing.unit_price expressed in the item's native UoM."""
    target = item if item is not None else getattr(cp, "item", None)
    return unit_price_in_item_uom(
        getattr(cp, "unit_price", None),
        getattr(cp, "unit_of_measure", None),
        target,
    )


def _pricing_row_is_current(cp, today: date | None = None) -> bool:
    """Active row with a unit price and effective window covering today."""
    if not getattr(cp, "is_active", True):
        return False
    if getattr(cp, "unit_price", None) is None:
        return False
    today_d = today or timezone.localdate()
    effective = getattr(cp, "effective_date", None)
    if effective and effective > today_d:
        return False
    expiry = getattr(cp, "expiry_date", None)
    if expiry and expiry < today_d:
        return False
    return True


def active_customer_pricing_by_item(customer, today: date | None = None) -> dict[int, Any]:
    """
    Latest current CustomerPricing row per item_id for a customer.

    Used by create-SO (picker + POST) so only profile-priced SKUs are orderable.
    """
    from .models import CustomerPricing

    today_d = today or timezone.localdate()
    by_item: dict[int, Any] = {}
    qs = (
        CustomerPricing.objects.filter(customer=customer, is_active=True)
        .select_related("item")
        .order_by("item_id", "-effective_date", "-id")
    )
    for cp in qs:
        if cp.item_id in by_item:
            continue
        if not _pricing_row_is_current(cp, today_d):
            continue
        by_item[cp.item_id] = cp
    return by_item
