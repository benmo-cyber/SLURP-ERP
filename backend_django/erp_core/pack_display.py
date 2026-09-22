"""Pack size display helpers (inventory table, batch tickets)."""
from __future__ import annotations

from typing import Any


def _fmt_num(value: float) -> str:
    v = float(value)
    if abs(v - round(v)) < 0.005:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _norm_uom(uom: str | None) -> str:
    u = (uom or "lbs").strip().lower()
    if u in ("lb", "lbs"):
        return "lbs"
    return u


def resolve_pack_size(
    *,
    item=None,
    lot=None,
    pack_size: float | None = None,
    pack_sizes: list[dict[str, Any]] | None = None,
    unit_of_measure: str | None = None,
) -> tuple[float | None, str | None]:
    """
    Resolve (pack_qty, pack_uom).

    Preference: lot.pack_size → ItemPackSize default → legacy Item.pack_size →
    pack_sizes list / pack_size kwargs (API payloads).
    """
    if lot is not None:
        lps = getattr(lot, "pack_size", None)
        if lps is not None and getattr(lps, "pack_size", None):
            return float(lps.pack_size), _norm_uom(getattr(lps, "pack_size_unit", None) or "lbs")

    if item is not None:
        try:
            qs = item.pack_sizes.filter(is_active=True).order_by("-is_default", "id")
            ps = qs.first()
            if ps is not None and ps.pack_size:
                return float(ps.pack_size), _norm_uom(ps.pack_size_unit)
        except Exception:
            pass
        if getattr(item, "pack_size", None):
            return float(item.pack_size), _norm_uom(
                getattr(item, "unit_of_measure", None) or unit_of_measure or "lbs"
            )

    if pack_sizes:
        default = next((p for p in pack_sizes if p.get("is_default")), None)
        chosen = default or pack_sizes[0]
        try:
            pv = float(chosen.get("pack_size") or 0)
        except (TypeError, ValueError):
            pv = 0.0
        if pv > 0:
            return pv, _norm_uom(chosen.get("pack_size_unit") or unit_of_measure or "lbs")

    if pack_size is not None:
        try:
            pv = float(pack_size)
        except (TypeError, ValueError):
            pv = 0.0
        if pv > 0:
            return pv, _norm_uom(unit_of_measure or "lbs")

    return None, None


def format_pack_label(
    *,
    item=None,
    lot=None,
    pack_size: float | None = None,
    pack_sizes: list[dict[str, Any]] | None = None,
    unit_of_measure: str | None = None,
    fallback_uom: str | None = None,
) -> str:
    """Human label like '50 lbs'. Falls back to UoM alone when pack size unknown."""
    pv, pu = resolve_pack_size(
        item=item,
        lot=lot,
        pack_size=pack_size,
        pack_sizes=pack_sizes,
        unit_of_measure=unit_of_measure or fallback_uom,
    )
    if pv is not None and pu:
        return f"{_fmt_num(pv)} {pu}"
    u = _norm_uom(fallback_uom or unit_of_measure)
    return u or "—"


def _convert_mass(qty: float, from_uom: str, to_uom: str) -> float:
    """Plant-standard lbs/kg conversion (``LBS_PER_KG`` = 2.2)."""
    from .mass_quantity import convert_mass_uom

    f = _norm_uom(from_uom)
    t = _norm_uom(to_uom)
    if f == t:
        return float(qty)
    if f in ("lbs", "kg") and t in ("lbs", "kg"):
        return float(convert_mass_uom(qty, f, t))
    return float(qty)


def format_packs_partial_note(
    qty: float,
    qty_uom: str,
    pack_qty: float | None,
    pack_uom: str | None,
) -> str:
    """
    Short pick-list note, e.g. '1 pk + 20 lb' or '2 pk'.

    Empty string when pack size is missing or not comparable.
    """
    if pack_qty is None or pack_qty <= 0 or qty is None:
        return ""
    q = float(qty)
    if q <= 0:
        return ""
    pu = _norm_uom(pack_uom)
    qu = _norm_uom(qty_uom)
    pack_in_qty_uom = pack_qty
    if pu in ("lbs", "kg") and qu in ("lbs", "kg") and pu != qu:
        pack_in_qty_uom = _convert_mass(pack_qty, pu, qu)
    elif pu != qu and pu not in ("lbs", "kg"):
        # Non-mass mismatch — skip rather than invent a conversion
        return ""

    if pack_in_qty_uom <= 0:
        return ""

    full = int(q // pack_in_qty_uom)
    rem = q - (full * pack_in_qty_uom)
    # Absorb float dust into full packs
    if rem < 0.05:
        rem = 0.0
    elif abs(rem - pack_in_qty_uom) < 0.05:
        full += 1
        rem = 0.0

    u_short = "lb" if qu == "lbs" else qu
    if full <= 0:
        return f"partial {_fmt_num(rem)} {u_short}"
    if rem <= 0:
        return f"{full} pk" if full != 1 else "1 pk"
    return f"{full} pk + {_fmt_num(rem)} {u_short}"


def is_partial_lot(lot, pack_qty: float | None = None, pack_uom: str | None = None) -> bool:
    """True when remaining qty is below one full pack (opened / partial pack)."""
    rem = float(getattr(lot, "quantity_remaining", 0) or 0)
    if rem <= 0:
        return False
    if pack_qty is None:
        item = getattr(lot, "item", None)
        pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)
    if not pack_qty or pack_qty <= 0:
        return False
    item = getattr(lot, "item", None)
    lot_uom = _norm_uom(getattr(item, "unit_of_measure", None) if item else "lbs")
    pack_in_lot = float(pack_qty)
    pu = _norm_uom(pack_uom)
    if pu in ("lbs", "kg") and lot_uom in ("lbs", "kg") and pu != lot_uom:
        pack_in_lot = _convert_mass(pack_qty, pu, lot_uom)
    return rem + 1e-6 < pack_in_lot
