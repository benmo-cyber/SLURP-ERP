"""Pack size display helpers (inventory table, batch tickets)."""
from __future__ import annotations

from typing import Any


def _fmt_num(value: float) -> str:
    v = float(value)
    if abs(v - round(v)) < 0.005:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _fmt_partial(value: float) -> str:
    """
    Remainder mass to the hundredth when fractional (e.g. 20.35, 12.50);
    whole pounds stay compact (15).
    """
    v = round(float(value), 2)
    if abs(v - round(v)) < 0.005:
        return str(int(round(v)))
    return f"{v:.2f}"


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


def pack_quantity_breakdown(
    qty: float,
    qty_uom: str,
    pack_qty: float | None,
    pack_uom: str | None,
) -> dict[str, Any] | None:
    """
    Split a mass into full packs + remainder.

    Returns None when pack size is missing or not comparable to qty UoM.
    Keys: full_packs, full_mass, remainder, pack_qty_in_uom, qty_uom, pack_label, note, display.
    """
    if pack_qty is None or pack_qty <= 0 or qty is None:
        return None
    q = float(qty)
    if q <= 0:
        return None
    pu = _norm_uom(pack_uom)
    qu = _norm_uom(qty_uom)
    pack_in_qty_uom = float(pack_qty)
    if pu in ("lbs", "kg") and qu in ("lbs", "kg") and pu != qu:
        pack_in_qty_uom = _convert_mass(pack_qty, pu, qu)
    elif pu != qu and pu not in ("lbs", "kg"):
        return None

    if pack_in_qty_uom <= 0:
        return None

    full = int(q // pack_in_qty_uom)
    rem = q - (full * pack_in_qty_uom)
    # Absorb float dust only (keep real hundredths on partials)
    if rem < 0.005:
        rem = 0.0
    elif abs(rem - pack_in_qty_uom) < 0.005:
        full += 1
        rem = 0.0
    else:
        rem = round(rem, 2)

    full_mass = full * pack_in_qty_uom
    u_short = "lb" if qu == "lbs" else qu
    u_long = "lbs" if qu == "lbs" else qu
    pack_label = f"{_fmt_num(pack_in_qty_uom)} {u_long}"

    if full <= 0:
        note = f"partial {_fmt_partial(rem)} {u_short}"
        display = f"{_fmt_partial(rem)} {u_long} partial"
    elif rem <= 0:
        note = f"{full} pk" if full != 1 else "1 pk"
        display = f"{full} × {pack_label}"
    else:
        note = f"{full} pk + {_fmt_partial(rem)} {u_short}"
        display = f"{full} × {pack_label} + {_fmt_partial(rem)} {u_long} partial"

    return {
        "full_packs": full,
        "full_mass": full_mass,
        "remainder": rem,
        "pack_qty_in_uom": pack_in_qty_uom,
        "qty_uom": qu,
        "pack_label": pack_label,
        "note": note,
        "display": display,
        "has_remainder": rem >= 0.01,
    }


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
    brk = pack_quantity_breakdown(qty, qty_uom, pack_qty, pack_uom)
    return brk["note"] if brk else ""


def format_packs_remnant_split_note(
    *,
    packs_qty: float | None,
    remnant_qty: float | None,
    qty_uom: str,
    pack_qty: float | None,
    pack_uom: str | None,
) -> str:
    """
    Pick-list note from the operator's packs vs remnant split (create-ticket fields).

    Prefer this over recomputing modulo pack size from the combined total, which
    reshuffles remnant (e.g. 16.04 lb remnant + 613.96 lb packs → wrong '28 pk + 14 lb').
    """
    qu = _norm_uom(qty_uom)
    u_short = "lb" if qu == "lbs" else qu
    packs = float(packs_qty or 0)
    remnant = float(remnant_qty or 0)
    if packs < 0.005 and remnant < 0.005:
        return ""

    packs_part = ""
    if packs >= 0.005:
        brk = pack_quantity_breakdown(packs, qu, pack_qty, pack_uom)
        if brk and brk.get("remainder", 0) < 0.005 and brk.get("full_packs", 0) > 0:
            n = int(brk["full_packs"])
            packs_part = f"{n} pk" if n != 1 else "1 pk"
        else:
            # Mass from sealed packs (not pack-count when qty isn't a whole pack).
            packs_part = f"{_fmt_partial(packs)} {u_short} from packs"

    rem_part = ""
    if remnant >= 0.005:
        rem_part = f"{_fmt_partial(remnant)} {u_short} partial"

    if packs_part and rem_part:
        return f"{packs_part} + {rem_part}"
    return packs_part or rem_part


def format_batch_input_packs_note(
    batch_input,
    *,
    qty_display: float,
    qty_uom: str,
    pack_qty: float | None = None,
    pack_uom: str | None = None,
) -> str:
    """Pick-list packs note for a batch input — honor stored packs/remnant when set."""
    item = batch_input.resolved_item() if hasattr(batch_input, "resolved_item") else None
    lot = getattr(batch_input, "lot", None)
    if pack_qty is None:
        pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)

    packs_native = getattr(batch_input, "quantity_packs", None)
    remnant_native = getattr(batch_input, "quantity_remnant", None)
    has_split = packs_native is not None or remnant_native is not None
    if has_split:
        native = _norm_uom(
            getattr(item, "unit_of_measure", None) if item else qty_uom
        )
        display = _norm_uom(qty_uom)

        def _to_display(q):
            if q is None:
                return 0.0
            q = float(q)
            if q <= 0:
                return 0.0
            if native in ("lbs", "kg") and display in ("lbs", "kg") and native != display:
                return _convert_mass(q, native, display)
            return q

        return format_packs_remnant_split_note(
            packs_qty=_to_display(packs_native),
            remnant_qty=_to_display(remnant_native),
            qty_uom=display,
            pack_qty=pack_qty,
            pack_uom=pack_uom,
        )

    return format_packs_partial_note(qty_display, qty_uom, pack_qty, pack_uom)

def lot_pack_breakdown(lot, *, qty: float | None = None, qty_uom: str | None = None) -> dict[str, Any] | None:
    """Breakdown for a lot's remaining (or provided) qty using resolved pack size."""
    item = getattr(lot, "item", None)
    pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)
    if qty is None:
        qty = float(getattr(lot, "quantity_remaining", 0) or 0)
    if qty_uom is None:
        qty_uom = _norm_uom(getattr(item, "unit_of_measure", None) if item else "lbs")
    return pack_quantity_breakdown(qty, qty_uom, pack_qty, pack_uom)


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


def lot_remnant_quantity(lot) -> float:
    """
    Remnant mass below full packs on a lot (same idea as Inventory → Partials).

    Returns 0 when there is no pack size or no remnant ≥ 0.01.
    Pure partial lots (remaining < one pack) return the full remaining qty.
    """
    brk = lot_pack_breakdown(lot)
    if not brk or not brk.get("has_remainder"):
        return 0.0
    return float(brk.get("remainder") or 0)


def _production_remnant_committed(lot, rem_phys: float) -> float:
    """
    How much of the physical remnant is claimed by in-progress production.

    Prefer stored ``ProductionBatchInput.quantity_remnant`` (create-ticket remnant
    field). When missing, consume each input's ``quantity_used`` from remnant
    first, then packs — never ``(physical - commit) % pack``, which invents a
    fake leftover after remnant + non-aligned packs (e.g. 7.29 rem + 279.07 packs
    → phantom 0.93 available).
    """
    from .models import ProductionBatchInput

    if rem_phys < 0.01:
        return 0.0
    rem_left = float(rem_phys)
    rem_taken = 0.0
    qs = (
        ProductionBatchInput.objects.filter(lot=lot, batch__status="in_progress")
        .order_by("id")
        .only("quantity_used", "quantity_remnant")
    )
    for inp in qs:
        if rem_left < 0.01:
            break
        stored = getattr(inp, "quantity_remnant", None)
        if stored is not None:
            take = min(rem_left, max(0.0, float(stored or 0)))
        else:
            take = min(rem_left, max(0.0, float(inp.quantity_used or 0)))
        rem_taken += take
        rem_left -= take
    return round(min(float(rem_phys), rem_taken), 2)


def lot_remnant_slices(
    lot,
    *,
    breakdown: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """
    Split physical remnant into free vs committed (sales / hold / production).

    Warehouse rule: open-bag remnant is consumed before sealed packs. Returns
    None when pack size is unknown. Keys are native lot UoM masses:
    rem_phys, rem_avail, rem_prod, rem_sales, rem_hold, full_phys, full_avail.
    """
    from .lot_display_quantities import compute_lot_quantity_breakdown

    item = getattr(lot, "item", None)
    lot_uom = _norm_uom(getattr(item, "unit_of_measure", None) if item else "lbs")
    pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)
    phys = float(getattr(lot, "quantity_remaining", 0) or 0)
    brk_phys = pack_quantity_breakdown(phys, lot_uom, pack_qty, pack_uom)
    if not brk_phys:
        return None

    bd = breakdown if breakdown is not None else compute_lot_quantity_breakdown(lot)
    sales_n = float(bd.get("allocated_to_sales") or 0)
    prod_n = float(bd.get("committed_to_production") or 0)
    hold_n = float(bd.get("quantity_on_hold") or 0)
    avail = float(bd.get("quantity_available_for_use") or 0)

    rem_phys = float(brk_phys.get("remainder") or 0)
    full_phys = float(brk_phys.get("full_mass") or 0)

    if rem_phys < 0.01:
        return {
            "rem_phys": 0.0,
            "rem_avail": 0.0,
            "rem_prod": 0.0,
            "rem_sales": 0.0,
            "rem_hold": 0.0,
            "full_phys": full_phys,
            "full_avail": max(0.0, avail),
        }

    # Pure remnant lot (no full packs): all commitments sit on the remnant.
    if full_phys < 0.01:
        rem_prod = min(rem_phys, prod_n)
        rem_sales = min(max(0.0, rem_phys - rem_prod), sales_n)
        rem_hold = min(max(0.0, rem_phys - rem_prod - rem_sales), hold_n)
        rem_avail = max(0.0, rem_phys - rem_prod - rem_sales - rem_hold)
        rem_avail = min(rem_avail, max(0.0, avail))
        return {
            "rem_phys": rem_phys,
            "rem_avail": round(rem_avail, 2),
            "rem_prod": round(rem_prod, 2),
            "rem_sales": round(rem_sales, 2),
            "rem_hold": round(rem_hold, 2),
            "full_phys": 0.0,
            "full_avail": 0.0,
        }

    # Mixed lot: production remnant from ticket split (or remnant-first);
    # sales/hold stay on the full-pack side (inventory Partials convention).
    rem_prod = min(rem_phys, _production_remnant_committed(lot, rem_phys), prod_n)
    rem_avail = max(0.0, rem_phys - rem_prod)
    rem_avail = min(rem_avail, max(0.0, avail))
    full_avail = max(0.0, avail - rem_avail)
    return {
        "rem_phys": rem_phys,
        "rem_avail": round(rem_avail, 2),
        "rem_prod": round(rem_prod, 2),
        "rem_sales": 0.0,
        "rem_hold": 0.0,
        "full_phys": full_phys,
        "full_avail": round(full_avail, 2),
    }


def lot_available_remnant_quantity(lot) -> float:
    """
    Free remnant after sales / hold / in-progress production commitments.

    Remnant-first (and stored ticket remnant when present) — not
    ``available % pack``, which invents leftover after a full remnant take.
    """
    slices = lot_remnant_slices(lot)
    if not slices:
        return 0.0
    rem = float(slices.get("rem_avail") or 0)
    return rem if rem >= 0.01 else 0.0
