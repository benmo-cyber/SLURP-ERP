"""Shared R&D formula list / save helpers for Quality and Finance workspaces."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from erp_core.models import Item, RDFormula, RDFormulaLine
from erp_core.rd_codes import allocate_rd_code

RD_LINE_ORDER = [
    ("ingredient", 1),
    ("ingredient", 2),
    ("ingredient", 3),
    ("ingredient", 4),
    ("ingredient", 5),
    ("packaging", 1),
    ("packaging", 2),
    ("packaging", 3),
    ("labor", 1),
]


def rd_lines_from_formula(rd: RDFormula | None) -> list[dict]:
    if rd is None:
        return [
            {
                "line_type": lt,
                "sequence": seq,
                "row_id": f"R{seq}" if lt == "ingredient" else ("Labor" if lt == "labor" else f"P{seq}"),
                "line": None,
            }
            for lt, seq in RD_LINE_ORDER
        ]
    by_key = {(l.line_type, l.sequence): l for l in rd.lines.select_related("item").all()}
    rows = []
    for lt, seq in RD_LINE_ORDER:
        line = by_key.get((lt, seq))
        rows.append(
            {
                "line_type": lt,
                "sequence": seq,
                "row_id": f"R{seq}" if lt == "ingredient" else ("Labor" if lt == "labor" else f"P{seq}"),
                "line": line,
            }
        )
    return rows


def rd_catalog_items():
    return Item.objects.filter(item_type__in=["raw_material", "distributed_item"]).order_by("sku")[:500]


def rd_formula_list_queryset(*, status: str, q: str):
    formulas = RDFormula.objects.prefetch_related("lines").order_by("-updated_at")
    if status == "active":
        formulas = formulas.filter(status__in=["draft", "approved"])
    elif status == "scrapped":
        formulas = formulas.filter(status="scrapped")
    elif status == "commercialized":
        formulas = formulas.filter(status="commercialized")
    if q:
        family_filter = Q()
        q_stripped = q.strip()
        if q_stripped.isalpha() and 1 <= len(q_stripped) <= 4:
            family_filter = Q(family_letter__iexact=q_stripped)
        formulas = formulas.filter(
            Q(name__icontains=q)
            | Q(rd_code__icontains=q)
            | Q(commercial_sku__icontains=q)
            | family_filter
        )
    return list(formulas[:300])


def rd_formula_counts() -> dict:
    return {
        "active": RDFormula.objects.filter(status__in=["draft", "approved"]).count(),
        "scrapped": RDFormula.objects.filter(status="scrapped").count(),
        "commercialized": RDFormula.objects.filter(status="commercialized").count(),
        "all": RDFormula.objects.count(),
    }


def rd_lines_payload_from_post(post) -> list[dict]:
    lines_payload = []
    for idx, (lt, seq) in enumerate(RD_LINE_ORDER):
        desc = (post.get(f"desc_{idx}") or "").strip()
        item_id = (post.get(f"item_{idx}") or "").strip()
        comp_raw = (post.get(f"comp_{idx}") or "").strip()
        price_raw = (post.get(f"price_{idx}") or "").strip()
        labor_raw = (post.get(f"labor_{idx}") or "").strip()
        notes = (post.get(f"notes_{idx}") or "").strip() or None
        if not desc and not item_id and not comp_raw and not price_raw and not labor_raw:
            continue
        lines_payload.append(
            {
                "line_type": lt,
                "sequence": seq,
                "item_id": int(item_id) if item_id else None,
                "description": desc,
                "composition_pct": float(comp_raw) if comp_raw else None,
                "price_per_lb": float(price_raw) if price_raw else None,
                "labor_flat_amount": float(labor_raw) if labor_raw else None,
                "notes": notes,
            }
        )
    return lines_payload


@transaction.atomic
def save_rd_formula(
    *,
    rd: RDFormula | None,
    name: str,
    status: str,
    notes: str | None,
    family_letter: str | None = None,
    lines_payload: list[dict],
) -> RDFormula:
    if rd is None:
        letter, code = allocate_rd_code(family_letter)
        rd = RDFormula.objects.create(
            name=name,
            family_letter=letter,
            rd_code=code,
            status=status or "draft",
            notes=notes,
        )
    else:
        new_status = (status or rd.status).strip()
        if rd.status == "commercialized" and new_status != "commercialized":
            new_status = "commercialized"
        rd.name = name
        rd.status = new_status
        rd.notes = notes
        rd.save()
        RDFormulaLine.objects.filter(rd_formula=rd).delete()
    for row in lines_payload:
        RDFormulaLine.objects.create(rd_formula=rd, **row)
    return rd
