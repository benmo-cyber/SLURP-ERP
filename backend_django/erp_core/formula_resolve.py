"""Resolve commercial Formula rows when an FG has multiple formulas."""
from __future__ import annotations

from .models import Formula, Lot, ProductionBatch, ProductionBatchOutput


def formulas_for_fg(finished_good_id: int):
    return Formula.objects.filter(finished_good_id=finished_good_id).order_by(
        "-is_default", "name", "id"
    )


def default_formula_for_fg(finished_good_id: int | None) -> Formula | None:
    if not finished_good_id:
        return None
    return (
        formulas_for_fg(finished_good_id)
        .prefetch_related("ingredients__item")
        .first()
    )


def formula_for_batch(batch: ProductionBatch | None) -> Formula | None:
    """Prefer the formula locked on the batch; else FG default."""
    if batch is None:
        return None
    if getattr(batch, "formula_id", None):
        f = getattr(batch, "formula", None)
        if f is not None:
            return f
        return (
            Formula.objects.filter(pk=batch.formula_id)
            .prefetch_related("ingredients__item")
            .first()
        )
    return default_formula_for_fg(batch.finished_good_item_id)


def formula_for_lot(lot: Lot | None) -> Formula | None:
    """Formula used to manufacture this lot, else FG default."""
    if lot is None:
        return None
    out = (
        ProductionBatchOutput.objects.filter(lot_id=lot.id)
        .select_related("batch", "batch__formula")
        .order_by("-id")
        .first()
    )
    if out and out.batch_id:
        return formula_for_batch(out.batch)
    return default_formula_for_fg(lot.item_id)


def formula_for_item(item_id: int | None) -> Formula | None:
    """Default formula for an FG item (shelf life, FPS, generic QC)."""
    return default_formula_for_fg(item_id)


def formula_label(formula: Formula | None) -> str:
    if formula is None:
        return ""
    name = (formula.name or "").strip() or "Standard"
    ver = (formula.version or "").strip()
    if ver:
        return f"{name} (v{ver})"
    return name


# Back-compat alias
recipe_label = formula_label
