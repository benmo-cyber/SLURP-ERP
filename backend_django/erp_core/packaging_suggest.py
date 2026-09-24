"""
Suggest packaging (container) EA counts from FG pack size and batch quantity.

Hint only — never enforced. L0040 → 40 lb; K0920 → 920 kg.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional, Tuple

_PACK_SUFFIX_RE = re.compile(r"^([KL])(\d{4})$", re.IGNORECASE)
_PACK_TAIL_RE = re.compile(r"([KL])(\d{4})$", re.IGNORECASE)

# Matches erp_core mass conversion used elsewhere
_LBS_PER_KG = 2.2046226218


def pack_net_from_item(item) -> Tuple[Optional[float], Optional[str]]:
    """
    Return (quantity, unit) for one full pack of this FG/DI SKU.

    unit is 'lbs' or 'kg'. Prefers sku_pack_suffix / SKU tail; falls back to Item.pack_size.
    """
    if item is None:
        return None, None

    suffix = (getattr(item, "sku_pack_suffix", None) or "").strip().upper()
    if not suffix:
        sku = (getattr(item, "sku", None) or "").strip().upper()
        m = _PACK_TAIL_RE.search(sku)
        if m:
            suffix = f"{m.group(1).upper()}{m.group(2)}"

    if suffix:
        m = _PACK_SUFFIX_RE.match(suffix)
        if m:
            letter = m.group(1).upper()
            qty = float(int(m.group(2)))
            if qty > 0:
                return qty, ("kg" if letter == "K" else "lbs")

    # Legacy Item.pack_size
    try:
        ps = float(getattr(item, "pack_size", None) or 0)
    except (TypeError, ValueError):
        ps = 0.0
    if ps > 0:
        uom = (getattr(item, "unit_of_measure", None) or "lbs").strip().lower()
        if uom in ("kg", "kgs", "kilogram", "kilograms"):
            return ps, "kg"
        return ps, "lbs"

    return None, None


def _to_display(qty: float, from_unit: str, display_uom: str) -> float:
    fu = (from_unit or "lbs").strip().lower()
    du = (display_uom or "lbs").strip().lower()
    if fu == du:
        return float(qty)
    if fu in ("kg", "kgs") and du in ("lbs", "lb"):
        return float(qty) * _LBS_PER_KG
    if fu in ("lbs", "lb") and du in ("kg", "kgs"):
        return float(qty) / _LBS_PER_KG
    return float(qty)


def suggested_container_count(
    batch_qty: float,
    *,
    pack_net: Optional[float],
    pack_unit: Optional[str] = None,
    display_uom: str = "lbs",
    epsilon: float = 1e-6,
) -> dict[str, Any]:
    """
    full = floor(batch / pack_net); partial = 1 if remainder else 0; suggested = full + partial.

    Returns dict with keys: suggested, full, partial, pack_net_display, pack_unit, ok.
    """
    out: dict[str, Any] = {
        "suggested": None,
        "full": 0,
        "partial": 0,
        "pack_net_display": None,
        "pack_unit": (pack_unit or display_uom or "lbs").lower(),
        "ok": False,
    }
    try:
        bq = float(batch_qty or 0)
    except (TypeError, ValueError):
        bq = 0.0
    if pack_net is None:
        return out
    try:
        pn = float(pack_net)
    except (TypeError, ValueError):
        return out
    if pn <= 0:
        return out

    pack_disp = _to_display(pn, pack_unit or "lbs", display_uom)
    if pack_disp <= 0:
        return out

    out["pack_net_display"] = round(pack_disp, 4)
    out["pack_unit"] = (display_uom or "lbs").lower()
    out["ok"] = True  # pack size known

    if bq <= 0:
        return out

    full = int(math.floor(bq / pack_disp + epsilon))
    rem = bq - (full * pack_disp)
    partial = 1 if rem > epsilon else 0
    # If batch is smaller than one pack, still need one container
    if full == 0 and bq > epsilon:
        partial = 1
    suggested = full + partial
    out.update(
        {
            "suggested": suggested,
            "full": full,
            "partial": partial,
            "pack_net_display": round(pack_disp, 4),
            "pack_unit": (display_uom or "lbs").lower(),
            "ok": True,
        }
    )
    return out


def suggested_containers_for_item(
    item, batch_qty: float, display_uom: str = "lbs"
) -> dict[str, Any]:
    """Convenience: pack_net_from_item + suggested_container_count."""
    net, unit = pack_net_from_item(item)
    return suggested_container_count(
        batch_qty, pack_net=net, pack_unit=unit, display_uom=display_uom
    )
