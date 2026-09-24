"""
Keep CostMaster in sync when catalog Items are created/updated.

Cost Master is a separate costing table (SKU + vendor). The API ItemViewSet already
created rows on item create; Slurp UI create/edit previously skipped that path.
"""
from __future__ import annotations

from typing import Any, Optional

from erp_core.models import CostMaster, CostMasterHistory, Item

LBS_PER_KG = 2.2


def _vendor_name(item: Item) -> Optional[str]:
    vendor = getattr(item, "vendor", None)
    if not vendor:
        # Plant utilities have no external vendor; still need a Cost Master key.
        if getattr(item, "plant_utility", False):
            return "Plant"
        return None
    if hasattr(vendor, "name"):
        return (vendor.name or "").strip() or None
    return str(vendor).strip() or None


def item_price_to_kg_lb(
    price: Any,
    unit_of_measure: Optional[str],
) -> tuple[Optional[float], Optional[float]]:
    """Return (price_per_kg, price_per_lb) from item unit price + UoM."""
    if price is None or price == "":
        return None, None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None, None
    uom = (unit_of_measure or "lbs").strip().lower()
    if uom == "lbs":
        return p * LBS_PER_KG, p
    if uom == "kg":
        return p, p / LBS_PER_KG
    return p, p


def sync_item_to_cost_master(
    item: Item,
    *,
    create_if_missing: bool = True,
    changed_by: Optional[str] = None,
    history_note: Optional[str] = None,
) -> Optional[CostMaster]:
    """
    Upsert CostMaster for this item's SKU + vendor.

    Returns the CostMaster row, or None when the item has no vendor (Cost Master
    is keyed by vendor material / vendor).
    """
    if not isinstance(item, Item):
        return None
    vendor_name = _vendor_name(item)
    if not vendor_name:
        return None
    sku = (item.sku or "").strip()
    if not sku:
        return None

    price_per_kg, price_per_lb = item_price_to_kg_lb(item.price, item.unit_of_measure)
    tariff = float(getattr(item, "tariff", None) or 0.0)
    hts = (getattr(item, "hts_code", None) or "").strip() or None
    origin = (getattr(item, "country_of_origin", None) or "").strip() or None

    defaults = {
        "vendor_material": item.name or sku,
        "price_per_kg": price_per_kg,
        "price_per_lb": price_per_lb,
        "tariff": tariff,
        "hts_code": hts,
        "origin": origin,
        "freight_per_kg": 0.0,
    }

    existing = CostMaster.objects.filter(
        wwi_product_code=sku, vendor=vendor_name
    ).first()

    if existing is None:
        if not create_if_missing:
            return None
        cm = CostMaster.objects.create(
            wwi_product_code=sku,
            vendor=vendor_name,
            **defaults,
        )
        return cm

    old_kg = existing.price_per_kg
    old_lb = existing.price_per_lb

    existing.vendor_material = item.name or existing.vendor_material
    if price_per_kg is not None:
        existing.price_per_kg = price_per_kg
    if price_per_lb is not None:
        existing.price_per_lb = price_per_lb
    if hts is not None:
        existing.hts_code = hts
    if origin is not None:
        existing.origin = origin
    # Only overwrite tariff when item carries a non-null tariff value we already resolved.
    existing.tariff = tariff if getattr(item, "tariff", None) is not None else (existing.tariff or 0.0)
    existing.calculate_landed_cost()
    existing.save()

    price_changed = (
        (price_per_kg is not None and old_kg != price_per_kg)
        or (price_per_lb is not None and old_lb != price_per_lb)
    )
    if price_changed:
        CostMasterHistory.objects.create(
            cost_master=existing,
            price_per_kg=existing.price_per_kg,
            price_per_lb=existing.price_per_lb,
            changed_by=changed_by or "system",
            notes=history_note
            or f"Synced from Item {sku}",
        )
    return existing
