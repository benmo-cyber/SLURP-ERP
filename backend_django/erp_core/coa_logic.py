"""COA line evaluation and release requirements (micro + QC)."""
from __future__ import annotations


def evaluate_item_line_pass(item_line, result_text: str) -> bool | None:
    """Return True/False pass, or None if not auto-evaluated."""
    raw = (result_text or "").strip()
    kind = getattr(item_line, "result_kind", None) or "text_only"

    if kind == "pass_fail":
        t = raw.lower()
        if t in ("pass", "ok", "yes", "acceptable", "negative"):
            return True
        if t in ("fail", "no", "reject", "rejected", "positive"):
            return False
        return None

    if kind == "text_only":
        return None

    try:
        cleaned = raw.replace("%", "").replace(",", "").strip()
        v = float(cleaned)
    except (TypeError, ValueError):
        return None

    if kind == "numeric_minimum":
        lo = getattr(item_line, "numeric_min", None)
        if lo is None:
            return None
        return v >= float(lo)

    if kind == "numeric_range":
        lo = getattr(item_line, "numeric_min", None)
        hi = getattr(item_line, "numeric_max", None)
        if lo is None and hi is None:
            return None
        if lo is not None and v < float(lo):
            return False
        if hi is not None and v > float(hi):
            return False
        return True

    return None


def evaluate_qc_numeric_pass(value: float | None, qmin: float | None, qmax: float | None) -> bool | None:
    if value is None:
        return None
    if qmin is not None and value < float(qmin):
        return False
    if qmax is not None and value > float(qmax):
        return False
    return True


def manufactured_item_types():
    return frozenset({"finished_good", "distributed_item"})


def lot_needs_coa_template(item) -> bool:
    from .models import ItemCoaTestLine

    return ItemCoaTestLine.objects.filter(item_id=item.id).exists()


def lot_has_formula_qc(item) -> bool:
    from .models import Formula

    try:
        f = Formula.objects.get(finished_good_id=item.id)
    except Formula.DoesNotExist:
        return False
    return bool((f.qc_parameter_name or "").strip())


def coa_required_for_full_release(lot) -> bool:
    it = getattr(lot, "item", None)
    if not it or getattr(it, "item_type", None) not in manufactured_item_types():
        return False
    return lot_needs_coa_template(it) or lot_has_formula_qc(it)


def qc_spec_display(qname: str, qmin: float | None, qmax: float | None) -> str:
    name = (qname or "").strip() or "QC"
    if qmin is not None and qmax is not None:
        return f"{name}: {qmin:g} – {qmax:g}"
    if qmin is not None:
        return f"NLT {qmin:g}% ({name})" if "%" not in name else f"NLT {qmin:g} ({name})"
    if qmax is not None:
        return f"NMT {qmax:g} ({name})"
    return name
