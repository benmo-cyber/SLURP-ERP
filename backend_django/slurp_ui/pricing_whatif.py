"""Customer pricing what-if: flat catalog, cost lookup, formula ingredient overrides."""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from erp_core.models import (
    CostMaster,
    PricingWhatIfLine,
    PricingWhatIfScenario,
    RDFormula,
    RDFormulaLine,
    VendorPricing,
)


def _norm(s: str | None) -> str:
    return " ".join((s or "").replace("\xa0", " ").split()).strip().lower()


def lookup_distributed_cost(product_name: str) -> tuple[float | None, CostMaster | None]:
    """Landed $/lb from Cost Master by WWI product code (then vendor material)."""
    needle = _norm(product_name)
    if not needle:
        return None, None
    qs = CostMaster.objects.exclude(wwi_product_code__isnull=True).exclude(wwi_product_code="")
    for cm in qs.iterator():
        if _norm(cm.wwi_product_code) == needle:
            return cm.landed_cost_per_lb or cm.price_per_lb, cm
    for cm in CostMaster.objects.iterator():
        if _norm(cm.vendor_material) == needle:
            return cm.landed_cost_per_lb or cm.price_per_lb, cm
    cm = (
        CostMaster.objects.filter(
            Q(wwi_product_code__icontains=product_name.strip())
            | Q(vendor_material__icontains=product_name.strip())
        )
        .order_by("-updated_at")
        .first()
    )
    if cm:
        return cm.landed_cost_per_lb or cm.price_per_lb, cm
    return None, None


def lookup_manufactured_cost(product_name: str) -> tuple[float | None, RDFormula | None]:
    """Formula $/lb from R&D / commercialized formulas."""
    needle = _norm(product_name)
    if not needle:
        return None, None
    formulas = RDFormula.objects.prefetch_related("lines").exclude(status="scrapped")
    for rd in formulas:
        candidates = [
            rd.name,
            rd.rd_code,
            rd.commercial_sku or "",
            f"{rd.name} ({rd.commercial_sku})" if rd.commercial_sku else "",
        ]
        for c in candidates:
            if _norm(c) == needle:
                return rd.total_cost_per_lb, rd
    rd = (
        formulas.filter(
            Q(name__icontains=product_name.strip())
            | Q(commercial_sku__icontains=product_name.strip())
            | Q(rd_code__icontains=product_name.strip())
        )
        .order_by("-updated_at")
        .first()
    )
    if rd:
        return rd.total_cost_per_lb, rd
    return None, None


def parse_catalog_key(key: str | None) -> tuple[str | None, int | None]:
    """Return (kind, id) for cm:12 / rd:5 keys."""
    raw = (key or "").strip()
    if ":" not in raw:
        return None, None
    kind, _, rest = raw.partition(":")
    kind = kind.strip().lower()
    try:
        pk = int(rest.strip())
    except ValueError:
        return None, None
    if kind in ("cm", "rd") and pk > 0:
        return kind, pk
    return None, None


def product_catalog() -> dict:
    """
    Flat catalog grouped for the picker.
    Entries: {key, value, label, kind, group}
      kind: distributed | rd | manufactured
      key: cm:<id> | rd:<id>
    """
    distributed: list[dict] = []
    for cm in CostMaster.objects.all().iterator():
        code = (cm.wwi_product_code or "").strip()
        mat = (cm.vendor_material or "").strip()
        if not code and not mat:
            continue
        label = code or mat
        if code and mat and mat.lower() != code.lower():
            label = f"{code} — {mat}"
        distributed.append(
            {
                "key": f"cm:{cm.pk}",
                "value": code or mat,
                "label": label,
                "kind": "distributed",
                "group": "Distributed (Cost Master)",
            }
        )
    distributed.sort(key=lambda x: x["label"].lower())

    rd_items: list[dict] = []
    mfg_items: list[dict] = []
    for rd in RDFormula.objects.exclude(status="scrapped").order_by("name"):
        if rd.commercial_sku:
            label = f"{rd.commercial_sku} — {rd.name} ({rd.rd_code})"
        else:
            label = f"{rd.name} ({rd.rd_code})"
        entry = {
            "key": f"rd:{rd.pk}",
            "value": rd.commercial_sku or rd.name or rd.rd_code,
            "label": label,
            "kind": "manufactured" if rd.status == "commercialized" else "rd",
            "group": (
                "Manufactured (commercialized R&D)"
                if rd.status == "commercialized"
                else "R&D formulas"
            ),
            "rd_code": rd.rd_code,
            "status": rd.status,
        }
        if rd.status == "commercialized":
            mfg_items.append(entry)
        else:
            rd_items.append(entry)

    flat = distributed + rd_items + mfg_items
    return {
        "distributed": distributed,
        "rd": rd_items,
        "manufactured": mfg_items,
        "flat": flat,
        # legacy shape used by older UI code
        "all": flat,
    }


def _override_map(overrides: dict | None) -> dict[str, dict]:
    if not overrides:
        return {}
    lines = overrides.get("lines") if isinstance(overrides, dict) else None
    if not isinstance(lines, dict):
        return {}
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in lines.items()}


def line_effective_price(line: RDFormulaLine, overrides: dict | None) -> float | None:
    ov = _override_map(overrides).get(str(line.pk)) or {}
    if ov.get("price_per_lb") not in (None, ""):
        try:
            return float(ov["price_per_lb"])
        except (TypeError, ValueError):
            pass
    if line.line_type == "labor":
        return None
    return float(line.price_per_lb) if line.price_per_lb is not None else None


def line_effective_cost(line: RDFormulaLine, overrides: dict | None) -> float:
    if line.line_type == "labor":
        ov = _override_map(overrides).get(str(line.pk)) or {}
        if ov.get("labor_flat_amount") not in (None, ""):
            try:
                return float(ov["labor_flat_amount"])
            except (TypeError, ValueError):
                pass
        return float(line.labor_flat_amount or 0)
    price = line_effective_price(line, overrides)
    pct = float(line.composition_pct or 0)
    if price is None:
        return 0.0
    return (pct / 100.0) * price


def compute_formula_cost(rd: RDFormula, overrides: dict | None = None) -> float:
    total = 0.0
    for line in rd.lines.all():
        total += line_effective_cost(line, overrides)
    return round(total, 4)


def vendor_cost_options_for_item(item_id: int | None) -> list[dict]:
    """Alternate $/lb sources for a formula ingredient Item."""
    if not item_id:
        return []
    today = timezone.now().date()
    opts: list[dict] = []
    seen: set[str] = set()

    vp_qs = VendorPricing.objects.filter(item_id=item_id, is_active=True).order_by(
        "-effective_date", "vendor_name"
    )
    for vp in vp_qs:
        if vp.expiry_date and vp.expiry_date < today:
            continue
        if vp.effective_date and vp.effective_date > today:
            continue
        key = f"vp:{vp.pk}"
        if key in seen:
            continue
        seen.add(key)
        # Assume unit_price is per the UOM; treat as $/lb when UOM is lbs/kg loosely.
        price = float(vp.unit_price or 0)
        uom = (vp.unit_of_measure or "lbs").lower()
        if uom in ("kg", "kgs", "kilogram", "kilograms"):
            price = price / 2.2
        opts.append(
            {
                "key": key,
                "label": f"{vp.vendor_name} list — ${price:.4f}/lb",
                "vendor_label": vp.vendor_name,
                "price_per_lb": round(price, 6),
                "source": "vendor_pricing",
            }
        )

    item = None
    try:
        from erp_core.models import Item

        item = Item.objects.filter(pk=item_id).first()
    except Exception:
        item = None
    if item:
        sku = (item.sku or "").strip()
        name = (item.name or "").strip()
        for needle in (sku, name):
            if not needle:
                continue
            cost, cm = lookup_distributed_cost(needle)
            if cm and cost is not None:
                key = f"cm:{cm.pk}"
                if key not in seen:
                    seen.add(key)
                    opts.append(
                        {
                            "key": key,
                            "label": f"Cost Master {cm.wwi_product_code or cm.vendor_material} — ${float(cost):.4f}/lb",
                            "vendor_label": cm.vendor or "Cost Master",
                            "price_per_lb": float(cost),
                            "source": "cost_master",
                        }
                    )
                break

    return opts


def formula_ingredient_payload(rd: RDFormula, overrides: dict | None = None) -> dict:
    rows = []
    for line in rd.lines.select_related("item").order_by("line_type", "sequence", "id"):
        ov = _override_map(overrides).get(str(line.pk)) or {}
        base_price = float(line.price_per_lb) if line.price_per_lb is not None else None
        eff_price = line_effective_price(line, overrides)
        eff_cost = line_effective_cost(line, overrides)
        rows.append(
            {
                "line_id": line.pk,
                "line_type": line.line_type,
                "sequence": line.sequence,
                "description": line.description or (line.item.name if line.item_id else "") or "",
                "item_id": line.item_id,
                "item_sku": line.item.sku if line.item_id else "",
                "composition_pct": line.composition_pct,
                "base_price_per_lb": base_price,
                "labor_flat_amount": line.labor_flat_amount,
                "effective_price_per_lb": eff_price,
                "effective_cost": round(eff_cost, 4),
                "override": ov,
                "vendor_options": vendor_cost_options_for_item(line.item_id)
                if line.line_type != "labor"
                else [],
            }
        )
    return {
        "rd_formula_id": rd.pk,
        "rd_code": rd.rd_code,
        "name": rd.name,
        "status": rd.status,
        "base_total_cost_per_lb": float(rd.total_cost_per_lb or 0),
        "effective_total_cost_per_lb": compute_formula_cost(rd, overrides),
        "lines": rows,
        "scenarios": [
            {"id": s.pk, "name": s.name}
            for s in PricingWhatIfScenario.objects.filter(rd_formula=rd).order_by("name")
        ],
    }


def resolve_catalog_selection(catalog_key: str | None = None, product_name: str | None = None, source_type: str | None = None):
    """Resolve catalog key / name into (kind, cost, cost_master, rd_formula, label)."""
    kind, pk = parse_catalog_key(catalog_key)
    if kind == "cm" and pk:
        cm = CostMaster.objects.filter(pk=pk).first()
        if cm:
            cost = cm.landed_cost_per_lb or cm.price_per_lb
            label = (cm.wwi_product_code or cm.vendor_material or "").strip()
            return "distributed", cost, cm, None, label
    if kind == "rd" and pk:
        rd = RDFormula.objects.prefetch_related("lines").filter(pk=pk).exclude(status="scrapped").first()
        if rd:
            st = "manufactured" if rd.status == "commercialized" else "rd"
            label = (rd.commercial_sku or rd.name or rd.rd_code).strip()
            return st, rd.total_cost_per_lb, None, rd, label

    # Fallback name search
    src = (source_type or "distributed").strip()
    name = (product_name or "").strip()
    if src in ("manufactured", "rd"):
        cost, rd = lookup_manufactured_cost(name)
        if rd:
            st = "manufactured" if rd.status == "commercialized" else "rd"
            return st, cost, None, rd, name
        cost, cm = lookup_distributed_cost(name)
        return "distributed", cost, cm, None, name
    cost, cm = lookup_distributed_cost(name)
    if cost is not None:
        return "distributed", cost, cm, None, name
    cost, rd = lookup_manufactured_cost(name)
    if rd:
        st = "manufactured" if rd.status == "commercialized" else "rd"
        return st, cost, None, rd, name
    return src or "distributed", None, None, None, name


def refresh_line_cost(line: PricingWhatIfLine, *, force: bool = False) -> PricingWhatIfLine:
    """Re-pull base cost from Cost Master or R&D (with ingredient overrides)."""
    if line.cost_is_manual and not force:
        return line

    if line.rd_formula_id and line.source_type in ("rd", "manufactured"):
        rd = line.rd_formula
        if rd is None:
            rd = RDFormula.objects.prefetch_related("lines").filter(pk=line.rd_formula_id).first()
        if rd:
            line.base_cost_per_lb = compute_formula_cost(rd, line.ingredient_overrides)
            line.cost_is_manual = False
            return line

    kind, cost, cm, rd, label = resolve_catalog_selection(
        catalog_key=line.catalog_key,
        product_name=line.product_name,
        source_type=line.source_type,
    )
    if label and not line.product_name:
        line.product_name = label
    line.source_type = kind if kind in ("distributed", "manufactured", "rd") else line.source_type
    line.cost_master = cm
    line.rd_formula = rd
    if rd and kind in ("rd", "manufactured"):
        line.base_cost_per_lb = compute_formula_cost(rd, line.ingredient_overrides)
        line.cost_is_manual = False
    elif cost is not None:
        line.base_cost_per_lb = float(cost)
        line.cost_is_manual = False
    return line


def compute_line_metrics(line: PricingWhatIfLine) -> dict:
    return {
        "unit_cost": line.unit_cost,
        "price_per_lb": line.price_per_lb,
        "annual_revenue": line.annual_revenue,
        "gross_profit": line.gross_profit,
        "weighted_revenue": line.weighted_revenue,
    }


def pipeline_totals(lines: list[PricingWhatIfLine]) -> dict:
    rev = 0.0
    gp = 0.0
    wrev = 0.0
    for line in lines:
        m = compute_line_metrics(line)
        if m["annual_revenue"] is not None:
            rev += m["annual_revenue"]
        if m["gross_profit"] is not None:
            gp += m["gross_profit"]
        if m["weighted_revenue"] is not None:
            wrev += m["weighted_revenue"]
    return {
        "revenue_total": rev,
        "gross_profit_total": gp,
        "gp_pct": (gp / rev) if rev else None,
        "weighted_revenue_total": wrev,
        "line_count": len(lines),
    }
