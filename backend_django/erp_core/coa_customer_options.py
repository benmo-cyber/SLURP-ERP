"""Resolve which master COA rows appear on a customer copy and how results display."""
from __future__ import annotations

from typing import Any


def _pass_fail_label(passes) -> str:
    if passes is True:
        return "Pass"
    if passes is False:
        return "Fail"
    return "—"


def _norm_test_name(name: str) -> str:
    return (name or "").strip().casefold()


def item_test_defaults_by_name(item) -> dict[str, dict[str, Any]]:
    """Map normalized test_name → {include, display, result_kind} from family COA template lines."""
    out: dict[str, dict[str, Any]] = {}
    if item is None:
        return out
    from .coa_template import coa_test_lines_for_item, resolve_coa_template_item

    template = resolve_coa_template_item(item)
    for line in coa_test_lines_for_item(template, select_related=None):
        key = _norm_test_name(line.test_name)
        if not key:
            continue
        kind = (line.result_kind or "text_only").strip().lower()
        disp = (line.customer_result_display or "actual").strip().lower()
        # Text-only tests have no auto pass/fail — customer PDF must show the actual result.
        if kind == "text_only":
            disp = "actual"
        out[key] = {
            "include": bool(line.include_on_customer_coa),
            "display": disp,
            "result_kind": kind,
            "catalog_test_id": getattr(line, "catalog_test_id", None),
        }
    return out


def customer_coa_requirements_by_name(customer, item) -> dict[str, dict[str, Any]]:
    """
    Active CustomerCoaRequirement rows for customer × family COA template item,
    keyed by normalized test_name.

    Values: specification_text (str|None), include (bool|None), display (str|'').
    """
    out: dict[str, dict[str, Any]] = {}
    if customer is None or item is None:
        return out
    from .coa_template import resolve_coa_template_item
    from .models import CustomerCoaRequirement

    template = resolve_coa_template_item(item)
    for req in CustomerCoaRequirement.objects.filter(
        customer=customer, item=template, is_active=True
    ):
        key = _norm_test_name(req.test_name)
        if not key:
            continue
        disp = (req.customer_result_display or "").strip().lower()
        if disp not in ("actual", "pass_fail"):
            disp = ""
        out[key] = {
            "specification_text": req.specification_text,
            "include": req.include_on_customer_coa,
            "display": disp,
            "catalog_test_id": req.catalog_test_id,
        }
    return out


def _customer_from_copy(copy):
    try:
        return copy.sales_order_lot.sales_order_item.sales_order.customer
    except Exception:
        return None


def apply_customer_coa_item_defaults(
    copy, certificate=None, *, force: bool = False, customer=None
) -> bool:
    """
    Populate include/display settings from ItemCoaTestLine (and customer requirements)
    when the copy has not been Customize-saved (or force=True). Returns True if fields
    were updated.
    """
    cert = certificate or copy.certificate
    if copy.customization_saved and not force:
        return False

    item = getattr(getattr(cert, "lot", None), "item", None)
    defaults = item_test_defaults_by_name(item)
    cust = customer if customer is not None else _customer_from_copy(copy)
    reqs = customer_coa_requirements_by_name(cust, item)

    for key, cfg in defaults.items():
        r = reqs.get(key)
        if not r:
            continue
        if r.get("include") is not None:
            cfg["include"] = bool(r["include"])
        if r.get("display") in ("actual", "pass_fail"):
            # Keep text_only forced to actual unless plant kind allows pass_fail
            if cfg.get("result_kind") == "text_only":
                cfg["display"] = "actual"
            else:
                cfg["display"] = r["display"]

    included: list[int] = []
    overrides: dict[str, str] = {}

    for lr in cert.line_results.all().order_by("id"):
        key = _norm_test_name(lr.test_name)
        cfg = defaults.get(key)
        if cfg is None:
            # No matching item template — include with actual (legacy-safe)
            # Still honor customer include/display if named match exists
            r = reqs.get(key)
            if r and r.get("include") is False:
                continue
            included.append(int(lr.id))
            disp = "actual"
            if r and r.get("display") in ("actual", "pass_fail"):
                disp = r["display"]
            overrides[str(lr.id)] = disp
            continue
        if cfg["include"]:
            included.append(int(lr.id))
            disp = cfg["display"] if cfg["display"] in ("actual", "pass_fail") else "actual"
            overrides[str(lr.id)] = disp

    # QC row: include when master has QC (default True)
    has_qc = bool(
        (cert.qc_parameter_name_snapshot or "").strip() or cert.qc_result_value is not None
    )
    include_qc = has_qc

    changed = (
        list(copy.included_line_result_ids or []) != included
        or bool(copy.include_qc_row) != include_qc
        or (copy.result_display_mode or "") != "per_line"
        or dict(copy.line_display_overrides or {}) != overrides
    )
    if not changed and not force:
        return False

    copy.included_line_result_ids = included
    copy.include_qc_row = include_qc
    copy.result_display_mode = "per_line"
    copy.line_display_overrides = overrides
    return True


def resolve_customer_spec_overrides(copy, certificate=None, customer=None) -> dict[str, str]:
    """
    Map line_result id (str) → printed Spec override from CustomerCoaRequirement.
    Only includes tests with a non-blank specification_text override.
    """
    cert = certificate or copy.certificate
    item = getattr(getattr(cert, "lot", None), "item", None)
    cust = customer if customer is not None else _customer_from_copy(copy)
    reqs = customer_coa_requirements_by_name(cust, item)
    if not reqs:
        return {}
    out: dict[str, str] = {}
    for lr in cert.line_results.all():
        key = _norm_test_name(lr.test_name)
        r = reqs.get(key)
        if not r:
            continue
        spec = r.get("specification_text")
        if spec is None:
            continue
        text = str(spec).strip()
        if not text:
            continue
        out[str(lr.id)] = text
    return out


def resolve_customer_coa_row_options(copy, certificate=None) -> dict[str, Any]:
    """Options for PDF row builder from a customer copy (apply defaults if needed)."""
    cert = certificate or copy.certificate
    if not copy.customization_saved and not (copy.included_line_result_ids or []):
        apply_customer_coa_item_defaults(copy, cert)

    mode = (copy.result_display_mode or "per_line").strip().lower()
    if mode not in ("actual", "pass_fail", "per_line"):
        mode = "per_line"

    include_ids = [int(x) for x in (copy.included_line_result_ids or []) if str(x).isdigit() or isinstance(x, int)]
    # If never customized and still empty after defaults attempt — include all
    if not copy.customization_saved and not include_ids:
        include_ids = list(cert.line_results.values_list("id", flat=True))

    return {
        "include_ids": include_ids,
        "include_qc": bool(copy.include_qc_row),
        "display_mode": mode,
        "line_overrides": {
            str(k): v
            for k, v in (copy.line_display_overrides or {}).items()
            if v in ("actual", "pass_fail")
        },
        "spec_overrides": resolve_customer_spec_overrides(copy, cert),
    }
