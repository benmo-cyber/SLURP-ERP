"""Helpers to feed slurp_ui Inventory Table from the same LotViewSet aggregations as React."""
from __future__ import annotations

from typing import Any

from rest_framework.test import APIRequestFactory, force_authenticate

from .mass_quantity import convert_mass_uom, normalize_aggregate_quantity_by_uom


def fetch_inventory_details(user, inventory_table: str) -> list[dict[str, Any]]:
    """Return SKU rows from ``LotViewSet.inventory_details`` (same payload as React)."""
    from .views import LotViewSet

    factory = APIRequestFactory()
    req = factory.get("/api/lots/inventory_details/", {"inventory_table": inventory_table})
    force_authenticate(req, user=user)
    view = LotViewSet.as_view({"get": "inventory_details"})
    response = view(req)
    data = response.data
    if isinstance(data, list):
        return data
    return []


def fetch_lots_by_sku_vendor(
    user,
    *,
    sku: str,
    vendor: str | None = None,
    inventory_table: str | None = None,
    deeper: bool = False,
) -> list[dict[str, Any]]:
    """Return lot rows from ``LotViewSet.lots_by_sku_vendor``."""
    from .views import LotViewSet

    params: dict[str, str] = {"sku": sku}
    if vendor is not None:
        params["vendor"] = vendor
    if inventory_table:
        params["inventory_table"] = inventory_table
    if deeper:
        params["deeper"] = "1"
    factory = APIRequestFactory()
    req = factory.get("/api/lots/lots_by_sku_vendor/", params)
    force_authenticate(req, user=user)
    view = LotViewSet.as_view({"get": "lots_by_sku_vendor"})
    response = view(req)
    data = response.data
    if isinstance(data, list):
        return data
    return []


def format_qty_for_display(
    quantity: float | int | None,
    storage_uom: str | None,
    display_uom: str,
) -> float:
    """Convert stored qty into display lbs/kg (ea unchanged)."""
    if quantity is None:
        return 0.0
    u = (storage_uom or "lbs").lower()
    d = (display_uom or "lbs").lower()
    if u == "ea" or d not in ("lbs", "kg"):
        return float(normalize_aggregate_quantity_by_uom(quantity, u))
    if u in ("lb", "lbs"):
        u = "lbs"
    if u == d or u not in ("lbs", "kg"):
        return float(normalize_aggregate_quantity_by_uom(quantity, u))
    return float(convert_mass_uom(quantity, u, d))
