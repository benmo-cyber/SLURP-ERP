"""Formula ingredient helpers — exact SKU vs parent-family lot matching."""
from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import FormulaItem, Item, Lot
from .sku_family import parse_sku_family


def parent_code_for_item(item: Item | None) -> str:
    """Best parent family code for an ingredient item."""
    if item is None:
        return ""
    code = (getattr(item, "sku_parent_code", None) or "").strip().upper()
    if code:
        return code
    sku = (getattr(item, "sku", None) or "").strip().upper()
    if not sku:
        return ""
    parent, _pack = parse_sku_family(
        sku,
        product_category=getattr(item, "product_category", None),
        item_type=getattr(item, "item_type", None),
    )
    return (parent or sku).strip().upper()


def skus_for_parent_code(parent_code: str) -> list[str]:
    """All item SKUs in a parent family (plus the bare parent code if present as a SKU)."""
    code = (parent_code or "").strip().upper()
    if not code:
        return []
    skus = set(
        Item.objects.filter(sku_parent_code__iexact=code).values_list("sku", flat=True)
    )
    skus.update(
        Item.objects.filter(sku__iexact=code).values_list("sku", flat=True)
    )
    # Also catch variants whose parent field is empty but SKU starts with parent+pack
    # Prefer explicit sku_parent_code; stem match is a safety net for older rows.
    if skus:
        return sorted(skus)
    # Fallback: parseable children only when no parent_code rows exist yet
    for it in Item.objects.filter(sku__istartswith=code).only(
        "sku", "sku_parent_code", "product_category", "item_type"
    )[:200]:
        p = parent_code_for_item(it)
        if p == code:
            skus.add(it.sku)
    return sorted(skus) if skus else [code]


def skus_for_formula_ingredient(ingredient: FormulaItem) -> list[str]:
    """
    SKUs whose lots may fulfill this formula line.

    match_by_parent=True → entire pack family (current + future variants).
    Otherwise → exact ingredient item SKU only.
    """
    item = getattr(ingredient, "item", None)
    if item is None:
        return []
    if getattr(ingredient, "match_by_parent", False):
        return skus_for_parent_code(parent_code_for_item(item))
    sku = (item.sku or "").strip()
    return [sku] if sku else []


def lots_for_formula_ingredient(
    ingredient: FormulaItem,
    *,
    limit: int | None = 80,
) -> QuerySet:
    """Available lots for a formula ingredient (exact or parent-expanded)."""
    skus = skus_for_formula_ingredient(ingredient)
    qs = (
        Lot.objects.filter(item__sku__in=skus, quantity_remaining__gt=0)
        .exclude(status="rejected")
        .select_related("item", "pack_size")
        .prefetch_related("item__pack_sizes")
        .order_by("-received_date")
    )
    if limit is not None:
        return qs[:limit]
    return qs


def representative_item_for_parent(parent_code: str) -> Item | None:
    """Pick a stable Item row to hang FormulaItem.item on for a parent selection."""
    code = (parent_code or "").strip().upper()
    if not code:
        return None
    qs = Item.objects.filter(
        Q(sku_parent_code__iexact=code) | Q(sku__iexact=code)
    ).order_by("sku")
    master = (
        qs.filter(Q(sku_pack_suffix__isnull=True) | Q(sku_pack_suffix=""))
        .order_by("sku")
        .first()
    )
    if master:
        return master
    exact = qs.filter(sku__iexact=code).first()
    if exact:
        return exact
    return qs.first()


def resolve_ingredient_select_value(raw: str) -> tuple[int, bool]:
    """
    Parse formula UI select value.

    ``p:D1300`` → (representative_item_id, match_by_parent=True)
    ``123`` → (item_id, match_by_parent=False)
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("Ingredient selection is empty")
    if s.lower().startswith("p:"):
        code = s[2:].strip().upper()
        item = representative_item_for_parent(code)
        if item is None:
            raise ValueError(f"No catalog items found for parent family {code}")
        return int(item.id), True
    return int(s), False


def ingredient_select_value(ingredient: FormulaItem) -> str:
    """Value to pre-select in formula UI for an existing FormulaItem."""
    if getattr(ingredient, "match_by_parent", False):
        code = parent_code_for_item(ingredient.item)
        if code:
            return f"p:{code}"
    return str(ingredient.item_id)


def build_parent_family_options(items: list[Item]) -> list[dict]:
    """Unique parent codes present among ingredient catalog items."""
    seen: dict[str, int] = {}
    for it in items:
        code = parent_code_for_item(it)
        if not code:
            continue
        seen[code] = seen.get(code, 0) + 1
    out = []
    for code in sorted(seen.keys()):
        out.append(
            {
                "value": f"p:{code}",
                "label": f"{code} — parent family (all pack sizes)",
                "code": code,
                "member_count": seen[code],
            }
        )
    return out
