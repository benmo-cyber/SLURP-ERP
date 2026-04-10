"""
Mass / batch quantity normalization.

Float drift from kg↔lbs conversions and summed inputs often yields 699.99 instead of 700.
We round to 2 decimal places, then snap to the nearest integer when within 0.01
(same tolerance as ProductionBatchInputSerializer.get_quantity_used).
"""
from __future__ import annotations

import math

# Match frontend + ProductionBatchInputSerializer integer snap (single line items)
MASS_INT_SNAP_TOLERANCE = 0.01

# Sums of rounded line qtys (SQL SUM, inventory totals) can land 0.02–0.05 off a whole number (e.g. 3149.96 vs 3150)
AGGREGATE_MASS_SNAP_TOLERANCE = 0.05


def normalize_mass_quantity(value: float | int | None) -> float:
    """
    Round to 2 dp, then if within MASS_INT_SNAP_TOLERANCE of a whole number, return that integer as float.
    """
    if value is None:
        return 0.0
    v = float(value)
    if not math.isfinite(v):
        return v
    v = round(v, 2)
    n = round(v)
    if abs(v - n) <= MASS_INT_SNAP_TOLERANCE:
        return float(n)
    return v


def normalize_quantity_by_uom(value: float | int | None, unit_of_measure: str | None) -> float:
    """
    Normalize API/display quantities: mass (lbs, kg, …) uses normalize_mass_quantity;
    ea uses integer snap or 5 dp (rolls) to match production input rounding.
    """
    if value is None:
        return 0.0
    u = (unit_of_measure or "").lower()
    if u == "ea":
        v = float(value)
        if not math.isfinite(v):
            return v
        ri = round(v)
        if abs(v - ri) <= MASS_INT_SNAP_TOLERANCE:
            return float(ri)
        return round(v, 5)
    return normalize_mass_quantity(value)


def normalize_aggregate_quantity_by_uom(value: float | int | None, unit_of_measure: str | None) -> float:
    """
    Use for SQL SUMs and inventory rollups only — wider snap so 3149.96 → 3150.
    Line-level storage/display still uses normalize_quantity_by_uom (0.01).
    """
    if value is None:
        return 0.0
    u = (unit_of_measure or "").lower()
    if u == "ea":
        v = float(value)
        if not math.isfinite(v):
            return v
        v = round(v, 5)
        ri = round(v)
        if abs(v - ri) <= AGGREGATE_MASS_SNAP_TOLERANCE:
            return float(ri)
        return v
    v = float(value)
    if not math.isfinite(v):
        return v
    v = round(v, 2)
    n = round(v)
    if abs(v - n) <= AGGREGATE_MASS_SNAP_TOLERANCE:
        return float(n)
    return v


def snap_stored_batch_input_quantity(value: float | int | None, unit_of_measure: str | None) -> float:
    """
    Persisted ProductionBatchInput.quantity_used: snap near-whole mass/ea with 0.05 tolerance
    so DB rows and SUM() match user intent (optional backfill / save hooks).
    """
    return normalize_aggregate_quantity_by_uom(value, unit_of_measure)
