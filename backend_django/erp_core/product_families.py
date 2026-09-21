"""Commercial pigment / product family codes (letter → display name).

Single-letter codes align with the leading family letter on natural-color SKUs
(e.g. D1307 → D Beet). Multi-letter R&D families (e.g. HL) may coexist.
"""
from __future__ import annotations

# Official WWI family letter numbering (I intentionally omitted).
PIGMENT_FAMILY_LETTERS: list[tuple[str, str]] = [
    ("A", "Purple Sweet potato"),
    ("B", "Cabbage"),
    ("C", "Black Carrot"),
    ("D", "Beet"),
    ("E", "Radish"),
    ("F", "Paprika"),
    ("G", "Beta Carotene"),
    ("H", "Turmeric"),
    ("J", "Chlorophyll"),
    ("K", "Spirulina Green"),
    ("L", "Spirulina Blue"),
    ("M", "Gardenia"),
    ("N", "Butterfly Pea"),
    ("O", "Grape"),
    ("P", "Annatto"),
    ("Q", "Carmine"),
]


def seed_pigment_product_families(*, apps=None) -> int:
    """Upsert A–Q family rows on RDFormulaFamily. Returns rows written."""
    if apps is not None:
        RDFormulaFamily = apps.get_model("erp_core", "RDFormulaFamily")
    else:
        from erp_core.models import RDFormulaFamily

    written = 0
    for code, name in PIGMENT_FAMILY_LETTERS:
        RDFormulaFamily.objects.update_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        written += 1
    return written


def backfill_item_product_families(*, apps=None, only_missing: bool = False) -> int:
    """
    Set Item.product_family from SKU / sku_parent_code leading family code.
    Longer codes win (e.g. HL before H). Returns number of items updated.
    """
    if apps is not None:
        Item = apps.get_model("erp_core", "Item")
        RDFormulaFamily = apps.get_model("erp_core", "RDFormulaFamily")
    else:
        from erp_core.models import Item, RDFormulaFamily

    families = list(RDFormulaFamily.objects.filter(is_active=True))
    families.sort(key=lambda f: (-len(f.code or ""), f.code or ""))
    if not families:
        return 0

    updated = 0
    qs = Item.objects.all()
    if only_missing:
        qs = qs.filter(product_family_id__isnull=True)

    for item in qs.iterator():
        stem = (getattr(item, "sku_parent_code", None) or item.sku or "").strip().upper()
        if not stem:
            continue
        matched = None
        for fam in families:
            code = (fam.code or "").strip().upper()
            if code and stem.startswith(code):
                matched = fam
                break
        if matched is None:
            continue
        if item.product_family_id == matched.id:
            continue
        item.product_family_id = matched.id
        # Historical models in migrations always have updated_at on Item.
        item.save(update_fields=["product_family_id", "updated_at"])
        updated += 1
    return updated
