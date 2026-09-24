"""
Cost Master workspace: segment Manufactured / Distributed / Raw,
with production Formula landed $/lb rollups for finished goods.
"""
from __future__ import annotations

from typing import Any, Optional

from django.db.models import Prefetch, Q

from erp_core.cost_master_sync import item_price_to_kg_lb
from erp_core.mass_quantity import LBS_PER_KG
from erp_core.models import CostMaster, Formula, FormulaItem, Item

SEGMENTS = ("manufactured", "distributed", "raw", "all")
DEFAULT_SEGMENT = "manufactured"


def _cm_landed_per_lb(cm: CostMaster | None) -> float | None:
    if cm is None:
        return None
    if cm.landed_cost_per_lb is not None:
        return float(cm.landed_cost_per_lb)
    # Ensure calc is current if save wasn't called
    cm.calculate_landed_cost()
    if cm.landed_cost_per_lb is not None:
        return float(cm.landed_cost_per_lb)
    return None


def _item_price_per_lb(item: Item) -> float | None:
    _, price_lb = item_price_to_kg_lb(getattr(item, "price", None), item.unit_of_measure)
    return price_lb


def cost_masters_for_sku(sku: str) -> list[CostMaster]:
    sku = (sku or "").strip()
    if not sku:
        return []
    return list(
        CostMaster.objects.filter(wwi_product_code=sku).order_by("-updated_at", "id")
    )


def pick_cost_master_for_item(item: Item) -> CostMaster | None:
    """Prefer vendor-matched CostMaster, else newest by SKU."""
    rows = cost_masters_for_sku(item.sku or "")
    if not rows:
        return None
    vendor_name = (getattr(item, "vendor", None) or "").strip()
    if vendor_name:
        for cm in rows:
            if (cm.vendor or "").strip().lower() == vendor_name.lower():
                return cm
    return rows[0]


def ingredient_landed_per_lb(item: Item) -> tuple[float | None, str]:
    """
    Return (landed $/lb, source) for an ingredient.
    Prefer Cost Master landed; fall back to Item catalog price as $/lb.
    """
    cm = pick_cost_master_for_item(item)
    landed = _cm_landed_per_lb(cm)
    if landed is not None:
        return landed, "cost_master"
    price_lb = _item_price_per_lb(item)
    if price_lb is not None:
        return float(price_lb), "item_price"
    return None, "missing"


def compute_formula_landed_cost(formula: Formula) -> dict[str, Any]:
    """
    Roll up production Formula to $/lb using ingredient landed costs.
    Returns total, missing flags, and line breakdown.
    """
    lines_out: list[dict[str, Any]] = []
    total = 0.0
    missing = 0
    for fi in formula.ingredients.all():
        pct = float(fi.percentage or 0)
        item = fi.item
        unit, source = ingredient_landed_per_lb(item)
        contrib = None
        if unit is not None:
            contrib = round((pct / 100.0) * unit, 6)
            total += contrib
        else:
            missing += 1
        lines_out.append(
            {
                "sku": item.sku,
                "name": item.name,
                "percentage": pct,
                "unit_cost_per_lb": unit,
                "contribution": contrib,
                "source": source,
                "match_by_parent": bool(fi.match_by_parent),
            }
        )
    return {
        "total_per_lb": round(total, 4) if lines_out and missing == 0 else (
            round(total, 4) if lines_out and missing < len(lines_out) else None
        ),
        "complete": missing == 0 and bool(lines_out),
        "missing_count": missing,
        "lines": lines_out,
    }


def _matches_search(haystacks: list[str | None], q: str) -> bool:
    if not q:
        return True
    s = q.lower()
    return any(s in (h or "").lower() for h in haystacks)


def _build_mfg_rows(q: str = "") -> list[dict[str, Any]]:
    formulas_qs = Formula.objects.prefetch_related(
        Prefetch(
            "ingredients",
            queryset=FormulaItem.objects.select_related("item"),
        )
    ).order_by("-is_default", "name", "id")

    items = (
        Item.objects.filter(item_type="finished_good")
        .prefetch_related(Prefetch("formulas", queryset=formulas_qs))
        .order_by("sku")
    )
    rows: list[dict[str, Any]] = []
    for item in items:
        if not _matches_search([item.sku, item.name], q):
            continue
        formula_rows: list[dict[str, Any]] = []
        default_cost: float | None = None
        for f in item.formulas.all():
            rollup = compute_formula_landed_cost(f)
            formula_rows.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "is_default": bool(f.is_default),
                    "version": f.version,
                    "cost_per_lb": rollup["total_per_lb"],
                    "complete": rollup["complete"],
                    "missing_count": rollup["missing_count"],
                    "lines": rollup["lines"],
                }
            )
            if f.is_default and rollup["total_per_lb"] is not None:
                default_cost = rollup["total_per_lb"]
        if default_cost is None and formula_rows:
            # First formula as baseline when none marked default
            for fr in formula_rows:
                if fr["cost_per_lb"] is not None:
                    default_cost = fr["cost_per_lb"]
                    break
        for fr in formula_rows:
            if fr["cost_per_lb"] is not None and default_cost is not None:
                fr["delta_vs_default"] = round(fr["cost_per_lb"] - default_cost, 4)
            else:
                fr["delta_vs_default"] = None
        rows.append(
            {
                "item": item,
                "sku": item.sku,
                "name": item.name,
                "formula_count": len(formula_rows),
                "default_cost_per_lb": default_cost,
                "formulas": formula_rows,
                "has_incomplete": any(not fr["complete"] for fr in formula_rows),
            }
        )
    return rows


def _annotate_purchase_row(cm: CostMaster, item: Item | None, actuals: dict) -> dict[str, Any]:
    a = actuals.get(cm.id) or actuals.get(str(cm.id)) or {}
    item_type = item.item_type if item else None
    return {
        "cm": cm,
        "id": cm.id,
        "sku": cm.wwi_product_code or (item.sku if item else ""),
        "name": (item.name if item else None) or cm.vendor_material,
        "vendor": cm.vendor or "",
        "item_type": item_type,
        "unlinked": item is None,
        "price_per_lb": cm.price_per_lb,
        "price_per_kg": cm.price_per_kg,
        "tariff": cm.tariff or 0.0,
        "freight_per_kg": cm.freight_per_kg or 0.0,
        "landed_cost_per_lb": cm.landed_cost_per_lb,
        "hts_code": cm.hts_code or "",
        "origin": cm.origin or "",
        "incoterms": cm.incoterms or "",
        "actual_comparison": a.get("comparison", "—"),
        "shipments_count": a.get("shipments_count", 0),
    }


def _build_purchase_rows(
    item_type: str | None,
    q: str,
    actuals: dict,
    *,
    include_unlinked: bool = False,
) -> list[dict[str, Any]]:
    """Purchase CostMaster rows filtered by linked Item.item_type."""
    items_by_sku: dict[str, Item] = {
        (it.sku or "").strip(): it
        for it in Item.objects.filter(
            item_type__in=["raw_material", "distributed_item"]
        )
        if (it.sku or "").strip()
    }
    qs = CostMaster.objects.exclude(wwi_product_code__isnull=True).exclude(wwi_product_code="")
    if q:
        qs = qs.filter(
            Q(vendor_material__icontains=q)
            | Q(wwi_product_code__icontains=q)
            | Q(vendor__icontains=q)
        )
    qs = qs.order_by("wwi_product_code", "vendor_material")[:800]

    rows: list[dict[str, Any]] = []
    for cm in qs:
        sku = (cm.wwi_product_code or "").strip()
        item = items_by_sku.get(sku)
        if item is None:
            if include_unlinked and item_type in (None, "raw_material"):
                if _matches_search([cm.vendor_material, cm.wwi_product_code, cm.vendor], q):
                    rows.append(_annotate_purchase_row(cm, None, actuals))
            continue
        if item_type and item.item_type != item_type:
            continue
        if not _matches_search([item.sku, item.name, cm.vendor, cm.vendor_material], q):
            continue
        rows.append(_annotate_purchase_row(cm, item, actuals))
    return rows


def cost_master_workspace(
    segment: str = DEFAULT_SEGMENT,
    q: str = "",
    *,
    actuals: dict | None = None,
) -> dict[str, Any]:
    """
    Build Cost Master tab payload.
    segment: manufactured | distributed | raw | all
    """
    seg = (segment or DEFAULT_SEGMENT).strip().lower()
    if seg not in SEGMENTS:
        seg = DEFAULT_SEGMENT
    q = (q or "").strip()
    actuals = actuals or {}

    mfg_rows: list[dict[str, Any]] = []
    dist_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []

    if seg in ("manufactured", "all"):
        mfg_rows = _build_mfg_rows(q)
    if seg in ("distributed", "all"):
        dist_rows = _build_purchase_rows("distributed_item", q, actuals)
    if seg in ("raw", "all"):
        raw_rows = _build_purchase_rows(
            "raw_material", q, actuals, include_unlinked=(seg == "raw" or seg == "all")
        )

    return {
        "segment": seg,
        "search": q,
        "mfg_rows": mfg_rows,
        "dist_rows": dist_rows,
        "raw_rows": raw_rows,
        "counts": {
            "manufactured": len(mfg_rows) if seg in ("manufactured", "all") else None,
            "distributed": len(dist_rows) if seg in ("distributed", "all") else None,
            "raw": len(raw_rows) if seg in ("raw", "all") else None,
        },
    }


def update_cost_master_purchase(
    cm_id: int,
    *,
    price_per_lb: Optional[float] = None,
    tariff: Optional[float] = None,
    freight_per_kg: Optional[float] = None,
) -> CostMaster:
    """Update editable purchase fields and recalculate landed cost."""
    cm = CostMaster.objects.get(pk=cm_id)
    if price_per_lb is not None:
        cm.price_per_lb = price_per_lb
        cm.price_per_kg = price_per_lb * LBS_PER_KG
    if tariff is not None:
        cm.tariff = tariff
    if freight_per_kg is not None:
        cm.freight_per_kg = freight_per_kg
    cm.calculate_landed_cost()
    cm.save()
    return cm
