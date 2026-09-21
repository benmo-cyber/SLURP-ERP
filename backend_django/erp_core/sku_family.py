"""
Parent / child SKU conventions — rules depend on product_category (and item_type for indirect).

Child (pack) suffix when present (all applicable categories):
  K or L + exactly four digits at end = pack quantity (lbs or kgs).

Natural colors, antioxidants, other:
  Parent = family prefix + material code.
  Family prefix is usually one letter (A–Q pigment lines), or a multi-letter blend code
  (registered on RDFormulaFamily, or composed from two single-letter families, e.g. L+H → LH).
  Optional K/L + four digits at end.

Synthetic colors:
  Parent = V + next four or five letters or digits (material stem). Same child suffix rules.

Indirect materials: no auto-parse.

When product_category is blank, still attempt pack-split using registered / composed family
codes and natural heuristics so parent codes appear for subsequent pack-line creates.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence, Tuple

_CHILD_PACK_RE = re.compile(r"([KL])(\d{4})$", re.IGNORECASE)
# Synthetic parent: V then exactly 4 or 5 alphanumeric (A-Z, 0-9); input normalized to uppercase before match.
_SYNTHETIC_PARENT_RE = re.compile(r"^V[A-Z0-9]{4,5}$")

# Categories that use the natural-color parent rules
_NATURAL_LIKE_CATEGORIES = frozenset({"natural_colors", "antioxidants", "other"})


def registered_family_codes() -> list[str]:
    """Active product-family codes from RDFormulaFamily, longest first (HL before H)."""
    try:
        from erp_core.models import RDFormulaFamily

        codes = [
            (c or "").strip().upper()
            for c in RDFormulaFamily.objects.filter(is_active=True).values_list("code", flat=True)
        ]
    except Exception:
        codes = []
    return sorted(
        {c for c in codes if c and c.isalpha() and 1 <= len(c) <= 4},
        key=lambda x: (-len(x), x),
    )


def composed_blend_codes(singles: Sequence[str] | None = None) -> list[str]:
    """
    Two-letter blend prefixes from pairs of distinct single-letter families (L+H → LH).
    Lets Natural Green LH01L0044 parse as parent LH01 without a pre-created LH row.
    """
    if singles is None:
        singles = [c for c in registered_family_codes() if len(c) == 1]
    else:
        singles = [c.strip().upper() for c in singles if c and len(c.strip()) == 1]
    out: list[str] = []
    for a in singles:
        for b in singles:
            if a != b:
                out.append(a + b)
    return out


def all_family_prefixes(codes: Sequence[str] | None = None) -> list[str]:
    """Registered codes plus composed two-letter blends, longest first."""
    registered = list(codes) if codes is not None else registered_family_codes()
    singles = [c for c in registered if len(c) == 1]
    combined = set(registered) | set(composed_blend_codes(singles))
    return sorted(combined, key=lambda x: (-len(x), x))


def match_family_prefix(stem: str, codes: Sequence[str] | None = None) -> Optional[str]:
    """Longest family code that prefixes stem."""
    s = (stem or "").strip().upper()
    if not s:
        return None
    if codes is None:
        ordered = all_family_prefixes()
    else:
        ordered = sorted(
            {(c or "").strip().upper() for c in codes if c},
            key=lambda x: (-len(x), x),
        )
    for code in ordered:
        if code and s.startswith(code):
            return code
    return None


def _natural_material_alphanumeric_ok(rest: str) -> bool:
    """
    Material code after the family letter (natural-like): at least four letters/digits, A-Z/0-9 only.
    Caller should pass uppercase rest (from SKU stem).
    """
    if len(rest) < 4:
        return False
    return all(c.isdigit() or ("A" <= c <= "Z") for c in rest)


def _norm_category(product_category: Optional[str]) -> str:
    return (product_category or "").strip().lower()


def _category_display_name(product_category: str) -> str:
    """Human label for messages (matches Item.PRODUCT_CATEGORY_CHOICES intent)."""
    key = _norm_category(product_category)
    labels = {
        "natural_colors": "Natural colors",
        "synthetic_colors": "Synthetic colors",
        "antioxidants": "Antioxidants",
        "other": "Other",
    }
    return labels.get(key, key.replace("_", " ").title() if key else "Unknown category")


def _rules_summary_for_category(product_category: str) -> str:
    """
    Short explanation of which SKU family rules apply for this product category.
    Used in warning copy so users see natural vs synthetic (etc.) explicitly.
    """
    key = _norm_category(product_category)
    if key == "synthetic_colors":
        return (
            "For Synthetic colors, the parent stem must be V plus 4 or 5 letters or digits (e.g. V1234 or V12AB). "
            "A pack variant may end with K or L and exactly four digits (e.g. …L0040)."
        )
    if key in _NATURAL_LIKE_CATEGORIES:
        return (
            "For Natural colors, Antioxidants, and Other, the parent stem is a family code (one letter, or a "
            "two-letter blend like LH from two pigment letters) plus a material code, "
            "with an optional K/L + four digits pack tail (e.g. D1307L0040 or LH01L0044)."
        )
    return "SKU family parsing depends on Product category; set Natural vs Synthetic colors so the correct rules apply."


def _diagnose_unparsed_with_pack_tail(sku: str, product_category: str) -> str:
    """
    When the SKU has a K/L+4 tail but parse_sku_family returned (None, None), explain why
    using the category-specific rules (not a generic message).
    """
    key = _norm_category(product_category)
    m = _CHILD_PACK_RE.search(sku)
    if not m:
        return ""
    parent = sku[: m.start()].strip().upper()
    if not parent:
        return "Nothing appears before the pack code (K/L + four digits); a parent stem is required."

    if key == "synthetic_colors":
        if _validate_synthetic_parent(parent):
            return (
                "The parent stem matches V + 4 or 5 letters/digits but parsing still failed - check for stray characters "
                "or inconsistent SKU formatting."
            )
        return (
            f"The part before the pack suffix is “{parent}”. For Synthetic colors that stem must be "
            f"V plus exactly 4 or 5 letters or digits (e.g. V1234 or V12AB), not the natural-color letter+material pattern."
        )

    if key in _NATURAL_LIKE_CATEGORIES:
        if validate_parent_sku(parent, strict_legacy=False) or validate_parent_sku_registered(parent):
            return (
                "The parent stem looks valid for natural-style rules but parsing failed - check SKU for "
                "extra characters or spacing."
            )
        detail_parts = []
        if len(parent) < 3:
            detail_parts.append("the stem is shorter than a family code plus material characters")
        elif not parent[0].isalpha():
            detail_parts.append("the stem does not start with a letter")
        else:
            detail_parts.append(
                "expected a family code (e.g. D or LH) plus material, then optional K/L+4 pack"
            )
        detail = "; ".join(detail_parts) if detail_parts else "the stem does not match the expected family + material pattern"
        return (
            f"The part before the pack suffix is “{parent}”. For {_category_display_name(key)}, {detail}."
        )

    return ""


def parse_sku_family(
    full_sku: str,
    *,
    product_category: Optional[str] = None,
    item_type: Optional[str] = None,
    family_codes: Sequence[str] | None = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Split SKU into (parent_code, pack_suffix). pack_suffix is e.g. L0040, or None for parent-only.

    Uses registered product-family codes and composed two-letter blends (e.g. LH) when available.
    indirect_material never parses.
    """
    s = (full_sku or "").strip().upper()
    if not s:
        return None, None
    if item_type == "indirect_material":
        return None, None

    prefixes = all_family_prefixes(family_codes) if family_codes is not None else all_family_prefixes()
    pc = (product_category or "").strip().lower()
    if pc == "synthetic_colors":
        return _parse_synthetic_family(s)

    # Prefer family-prefix-aware parse (single or multi-letter) for natural-like + uncategorized.
    parsed = _parse_registered_family(s, prefixes)
    if parsed != (None, None):
        return parsed

    if pc in _NATURAL_LIKE_CATEGORIES:
        return _parse_natural_family(s)

    # No category: still accept classic single-letter natural parent / pack shapes.
    return _parse_natural_family(s)


def _parse_synthetic_family(s: str) -> Tuple[Optional[str], Optional[str]]:
    """Parent = V + 4 or 5 alphanumeric; optional child K/L + 4 digits."""
    m = _CHILD_PACK_RE.search(s)
    if m:
        pack = f"{m.group(1).upper()}{m.group(2)}"
        parent = s[: m.start()]
        if parent and _validate_synthetic_parent(parent):
            return parent, pack
        return None, None
    if _validate_synthetic_parent(s):
        return s, None
    return None, None


def _validate_synthetic_parent(p: str) -> bool:
    u = (p or "").strip().upper()
    return bool(_SYNTHETIC_PARENT_RE.match(u))


def _parse_registered_family(
    s: str, codes: Sequence[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Split using family prefixes (longest match), then optional K/L+4 pack."""
    m = _CHILD_PACK_RE.search(s)
    if m:
        pack = f"{m.group(1).upper()}{m.group(2)}"
        parent = s[: m.start()]
        if parent and validate_parent_sku_registered(parent, codes=codes):
            return parent, pack
        # Ambiguous tails (e.g. HL1301 looks like H + L1301 pack) — try full stem as parent.
    if validate_parent_sku_registered(s, codes=codes):
        return s, None
    return None, None


def _parse_natural_family(s: str) -> Tuple[Optional[str], Optional[str]]:
    """Natural / antioxidant / other: one letter + material (digits or 4+ alnum); optional child K/L + 4 digits."""
    m = _CHILD_PACK_RE.search(s)
    if m:
        pack = f"{m.group(1).upper()}{m.group(2)}"
        parent = s[: m.start()]
        if parent and validate_parent_sku(parent, strict_legacy=False):
            return parent, pack
        # Same ambiguity as registered path — prefer full stem when pack split fails.
    if _looks_like_parent_only_natural(s):
        return s, None
    if validate_parent_sku(s, strict_legacy=False):
        return s, None
    return None, None


def _looks_like_parent_only_natural(s: str) -> bool:
    s = (s or "").strip().upper()
    if len(s) < 5:
        return False
    if not s[0].isalpha():
        return False
    if _CHILD_PACK_RE.search(s):
        return False
    rest = s[1:]
    if not rest:
        return False
    if rest.isdigit():
        return validate_parent_material_code(rest, strict_legacy=True)
    return _natural_material_alphanumeric_ok(rest)


def validate_parent_material_code(material_digits: str, *, strict_legacy: bool = True) -> bool:
    if not material_digits:
        return False
    if strict_legacy:
        if len(material_digits) < 4 or not material_digits.isdigit():
            return False
        if material_digits[0] not in "123":
            return False
        if material_digits[1] not in "34":
            return False
        return True
    if len(material_digits) < 4:
        return False
    if material_digits[0] not in "123":
        return False
    if material_digits[1] not in "34":
        return False
    return True


def validate_parent_sku(parent: str, *, strict_legacy: bool = True) -> bool:
    """
    Natural-family parent: one family letter + material code.
    Legacy: all-digit material (strict position rules). Extended: 4+ letters/digits (e.g. YM100).
    """
    p = (parent or "").strip().upper()
    if len(p) < 5:
        return False
    if not p[0].isalpha():
        return False
    rest = p[1:]
    if not rest:
        return False
    if rest.isdigit():
        return validate_parent_material_code(rest, strict_legacy=strict_legacy)
    return _natural_material_alphanumeric_ok(rest)


def validate_parent_sku_registered(
    parent: str, *, codes: Sequence[str] | None = None
) -> bool:
    """
    Parent stem valid under registered / composed family codes.
    Multi-letter families (LH, HL): family + at least 2 alphanumeric material chars (e.g. LH01).
    Single-letter: existing natural rules (e.g. D1307).
    """
    p = (parent or "").strip().upper()
    if not p or not p[0].isalpha():
        return False
    code_list = list(codes) if codes is not None else all_family_prefixes()
    fam = match_family_prefix(p, code_list)
    if not fam:
        return validate_parent_sku(p, strict_legacy=False)
    rest = p[len(fam) :]
    if not rest:
        return False
    if len(fam) >= 2:
        # Blend / multi-letter family: allow shorter material (LH01, HL1301).
        return len(rest) >= 2 and all(c.isalnum() for c in rest)
    if rest.isdigit():
        return validate_parent_material_code(rest, strict_legacy=False)
    return _natural_material_alphanumeric_ok(rest)


def item_sku_family_warnings(item) -> list[dict]:
    """
    Flags for UI when SKU family data may need attention.
    Returns a list of {"code": str, "message": str, "hint": str optional}.
    Messages reference Product category (natural vs synthetic, etc.) so the correct rule set is clear.
    """
    warnings: list[dict] = []
    if getattr(item, "item_type", None) == "indirect_material":
        return warnings

    sku = (getattr(item, "sku", None) or "").strip()
    if not sku:
        return warnings

    pc = _norm_category(getattr(item, "product_category", None))
    it = getattr(item, "item_type", None)

    sp = (getattr(item, "sku_parent_code", None) or "").strip().upper() or None
    ss = (getattr(item, "sku_pack_suffix", None) or "").strip().upper() or None
    has_pack_tail = bool(_CHILD_PACK_RE.search(sku))

    # No category: cannot choose natural vs synthetic rules — only nudge when SKU clearly uses family shape.
    if not pc:
        if has_pack_tail or sp or ss:
            warnings.append(
                {
                    "code": "missing_product_category",
                    "message": "Set Product category so SKU family rules can be applied.",
                    "hint": (
                        "Natural colors, Antioxidants, and Other use one rule set (letter + material digits; optional K/L+4 pack tail). "
                        "Synthetic colors uses another (V + 4-5 letters or digits; optional K/L+4). "
                        "Choose the category that matches this item, then save or run populate_sku_family_fields."
                    ),
                }
            )
        return warnings

    cat_label = _category_display_name(pc)
    rules_sentence = _rules_summary_for_category(pc)

    parsed = parse_sku_family(sku, product_category=pc, item_type=it)
    p, suf = parsed
    p_u = p.upper() if p else None
    suf_u = suf.upper() if suf else None

    if p is None and suf is None:
        if has_pack_tail:
            detail = _diagnose_unparsed_with_pack_tail(sku, pc)
            warnings.append(
                {
                    "code": "unparsed_pack_suffix",
                    "message": (
                        f"SKU pack tail (K/L + four digits) does not form a valid family with the parent stem "
                        f"for {cat_label}."
                    ),
                    "hint": (
                        f"{rules_sentence} "
                        f"{detail + ' ' if detail else ''}"
                        f"If the category is wrong, change Product category to Natural vs Synthetic colors (etc.) and save. "
                        f"Otherwise adjust the SKU or run populate_sku_family_fields."
                    ),
                }
            )
        if sp or ss:
            warnings.append(
                {
                    "code": "stored_family_no_parse",
                    "message": (
                        f"Stored parent/suffix fields do not match a parseable SKU for {cat_label}."
                    ),
                    "hint": (
                        f"{rules_sentence} "
                        f"The database has sku_parent_code or sku_pack_suffix, but the full SKU cannot be parsed under this category. "
                        f"Fix: confirm Product category matches how the SKU was built, then align the SKU text with {_category_display_name(pc)} rules, save the item, or re-run populate_sku_family_fields."
                    ),
                }
            )
    else:
        # Parsed OK: only warn when stored DB fields disagree (bad backfill / manual edit), not when empty.
        if sp or ss:
            if sp and p_u and sp != p_u:
                warnings.append(
                    {
                        "code": "parent_code_mismatch",
                        "message": (
                            f"Stored parent code does not match the parent stem implied by the SKU ({cat_label} rules)."
                        ),
                        "hint": (
                            f"{rules_sentence} "
                            f"sku_parent_code in the database should match the parent part of the SKU before any K/L+4 pack tail. "
                            f"Fix: save the item to refresh family fields, run populate_sku_family_fields, or set parent/suffix to match the SKU."
                        ),
                    }
                )
            if (ss or "") != (suf_u or ""):
                warnings.append(
                    {
                        "code": "pack_suffix_mismatch",
                        "message": (
                            f"Stored pack suffix does not match the K/L+4 tail implied by the SKU ({cat_label})."
                        ),
                        "hint": (
                            f"{rules_sentence} "
                            f"sku_pack_suffix should be exactly the K or L plus four digits at the end of the SKU when a pack variant is present. "
                            f"Fix: save the item, run the backfill command, or clear or correct the suffix field."
                        ),
                    }
                )

    return warnings


def apply_parsed_family_to_item(item, *, commit: bool = False) -> bool:
    from django.apps import apps

    Item = apps.get_model("erp_core", "Item")
    if not isinstance(item, Item):
        return False
    if getattr(item, "item_type", None) == "indirect_material":
        return False

    parent, pack = parse_sku_family(
        item.sku or "",
        product_category=getattr(item, "product_category", None),
        item_type=getattr(item, "item_type", None),
    )
    if not parent:
        return False

    item.sku_parent_code = parent.upper()
    item.sku_pack_suffix = pack.upper() if pack else None
    if commit:
        item.save(update_fields=["sku_parent_code", "sku_pack_suffix"])
    return True
