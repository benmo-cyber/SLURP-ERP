"""
Resolve which Item holds the FPS COA template (ItemCoaTestLine) for a pack family.

Parent families share one COA master; pack variants inherit those lines.
CustomerCoaRequirement rows are keyed to the same template item.
"""
from __future__ import annotations

from typing import Optional

from django.db import transaction
from django.db.models import Count, Q

from erp_core.sku_family import parse_sku_family


def fps_parent_code(item) -> str:
    """Material family / parent SKU (e.g. D1307, P2408); falls back to parse or full SKU."""
    if item is None:
        return ""
    code = (getattr(item, "sku_parent_code", None) or "").strip().upper()
    if code:
        return code
    parent, _pack = parse_sku_family(
        getattr(item, "sku", None) or "",
        product_category=getattr(item, "product_category", None),
        item_type=getattr(item, "item_type", None),
    )
    return (parent or getattr(item, "sku", None) or "").strip().upper()


def family_items(item, *, limit: int = 200) -> list:
    """FG/DI catalog rows sharing this item's parent code (deduped by full SKU)."""
    from erp_core.models import Item

    if item is None:
        return []
    parent = fps_parent_code(item)
    if not parent:
        return [item]

    qs = Item.objects.filter(item_type__in=["finished_good", "distributed_item"]).annotate(
        _coa_n=Count("coa_test_lines")
    )
    # Prefer stored parent; also include parse fallback via scan of matching parent code
    candidates = list(
        qs.filter(
            Q(sku_parent_code__iexact=parent) | Q(sku__istartswith=parent)
        ).order_by("sku", "id")[:limit]
    )
    members = [it for it in candidates if fps_parent_code(it) == parent]
    if not members:
        members = [item]

    # Collapse duplicate Item rows with the same full SKU (prefer more COA lines, then lowest id)
    by_sku: dict[str, object] = {}
    for it in members:
        key = (it.sku or "").strip().upper() or f"__ID_{it.id}"
        prev = by_sku.get(key)
        if prev is None:
            by_sku[key] = it
            continue
        prev_n = int(getattr(prev, "_coa_n", 0) or 0)
        cur_n = int(getattr(it, "_coa_n", 0) or 0)
        if cur_n > prev_n or (cur_n == prev_n and it.id < prev.id):
            by_sku[key] = it
    return sorted(by_sku.values(), key=lambda x: ((x.sku or "").upper(), x.id))


def _default_template_among(members: list):
    """Heuristic when no explicit coa_template_item pointers exist."""
    if not members:
        return None
    if len(members) == 1:
        return members[0]

    # Prefer rows that other members point to via sku_parent_item
    pointed_ids = {m.sku_parent_item_id for m in members if m.sku_parent_item_id}
    for m in members:
        if m.id in pointed_ids:
            return m

    # Prefer empty pack suffix (true master / parent-only row)
    for m in members:
        if not (m.sku_pack_suffix or "").strip():
            return m

    # Prefer SKU equal to parent code
    parent = fps_parent_code(members[0])
    for m in members:
        if (m.sku or "").strip().upper() == parent:
            return m

    # Prefer most existing COA lines
    best = max(
        members,
        key=lambda x: (int(getattr(x, "_coa_n", 0) or 0), -(x.id or 0)),
    )
    if int(getattr(best, "_coa_n", 0) or 0) > 0:
        return best

    return sorted(members, key=lambda x: ((x.sku or "").upper(), x.id))[0]


def resolve_coa_template_item(item):
    """
    Item whose ItemCoaTestLine rows define the FPS COA for this SKU / family.
    """
    if item is None:
        return None

    # Explicit pointer on this row
    src_id = getattr(item, "coa_template_item_id", None)
    if src_id:
        src = getattr(item, "coa_template_item", None)
        if src is not None:
            return src
        from erp_core.models import Item

        return Item.objects.filter(pk=src_id).first() or item

    members = family_items(item)
    if len(members) <= 1:
        return item

    # If siblings explicitly point at a master, honor that
    votes: dict[int, int] = {}
    for m in members:
        tid = getattr(m, "coa_template_item_id", None)
        if tid:
            votes[tid] = votes.get(tid, 0) + 1
    if votes:
        best_id = max(votes, key=votes.get)
        for m in members:
            if m.id == best_id:
                return m

    return _default_template_among(members) or item


def coa_test_lines_for_item(item, *, select_related: Optional[tuple] = ("catalog_test",)):
    """Ordered ItemCoaTestLine queryset/list for the resolved template item."""
    from erp_core.models import ItemCoaTestLine

    template = resolve_coa_template_item(item)
    if template is None:
        return ItemCoaTestLine.objects.none()
    qs = ItemCoaTestLine.objects.filter(item=template).order_by("sort_order", "id")
    if select_related:
        qs = qs.select_related(*select_related)
    return qs


def item_has_coa_template_lines(item) -> bool:
    return coa_test_lines_for_item(item, select_related=None).exists()


@transaction.atomic
def set_family_coa_template(master) -> object:
    """
    Make ``master`` the COA template for its parent family.

    - Clears master.coa_template_item
    - Points every other family member at master
    - Moves ItemCoaTestLine rows onto master if master has none but a sibling does
    """
    from erp_core.models import Item, ItemCoaTestLine

    if master is None:
        raise ValueError("master item is required")

    members = family_items(master)
    member_ids = [m.id for m in members]
    if master.id not in member_ids:
        members = list(members) + [master]
        member_ids.append(master.id)

    # Move lines onto master if needed
    master_line_n = ItemCoaTestLine.objects.filter(item_id=master.id).count()
    if master_line_n == 0:
        donors = (
            ItemCoaTestLine.objects.filter(item_id__in=member_ids)
            .exclude(item_id=master.id)
            .values("item_id")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        donor_row = donors.first()
        if donor_row and donor_row["n"]:
            ItemCoaTestLine.objects.filter(item_id=donor_row["item_id"]).update(item_id=master.id)

    Item.objects.filter(pk=master.id).update(coa_template_item=None)
    Item.objects.filter(pk__in=member_ids).exclude(pk=master.id).update(coa_template_item_id=master.id)

    # Refresh
    return Item.objects.get(pk=master.id)
