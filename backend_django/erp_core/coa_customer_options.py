"""Resolve which master COA rows appear on a customer copy and how results display."""
from __future__ import annotations

from typing import Any


def _pass_fail_label(passes) -> str:
    if passes is True:
        return "Pass"
    if passes is False:
        return "Fail"
    return "—"


def item_test_defaults_by_name(item) -> dict[str, dict[str, Any]]:
    """Map normalized test_name → {include, display} from ItemCoaTestLine."""
    out: dict[str, dict[str, Any]] = {}
    if item is None:
        return out
    for line in item.coa_test_lines.all():
        key = (line.test_name or "").strip().casefold()
        if not key:
            continue
        out[key] = {
            "include": bool(line.include_on_customer_coa),
            "display": (line.customer_result_display or "actual").strip().lower(),
        }
    return out


def apply_customer_coa_item_defaults(copy, certificate=None, *, force: bool = False) -> bool:
    """
    Populate include/display settings from ItemCoaTestLine when the copy has not
    been Customize-saved (or force=True). Returns True if fields were updated.
    """
    cert = certificate or copy.certificate
    if copy.customization_saved and not force:
        return False

    item = getattr(getattr(cert, "lot", None), "item", None)
    defaults = item_test_defaults_by_name(item)
    included: list[int] = []
    overrides: dict[str, str] = {}

    for lr in cert.line_results.all().order_by("id"):
        key = (lr.test_name or "").strip().casefold()
        cfg = defaults.get(key)
        if cfg is None:
            # No matching item template — include with actual (legacy-safe)
            included.append(int(lr.id))
            overrides[str(lr.id)] = "actual"
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
    }
