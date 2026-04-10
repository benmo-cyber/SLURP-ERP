"""
Finished Product Specification (FPS) PDF: Jinja2 HTML → xhtml2pdf (same flow as PO/invoice).
"""
from pathlib import Path
import logging

from .html_pdf_common import html_string_to_pdf_bytes
from .pdf_generator import get_batch_ticket_logo_base64_cached

logger = logging.getLogger(__name__)

FPS_FOOTER_NOTE = (
    "This document contains confidential and proprietary information intended solely for the recipient. "
    "By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, "
    "distribute, or use any information herein for purposes other than those expressly authorized. "
    "Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, "
    "please notify the sender immediately and delete this document from your system "
    "Finished Product Specification Form – Updated 12/10/2025 (GDM) – Reviewed by GDM – Effective Date 12/10/2025 – Doc No. 3.3 - 01."
)


def _s(val):
    """Plain string for template (Jinja autoescape)."""
    if val is None:
        return ""
    return str(val)


def _build_fps_context(fps):
    """Build template context from FinishedProductSpecification + related Item + Formula."""
    from .models import Formula

    item = fps.item
    sku = _s(getattr(item, "sku", "") or "")
    name = _s(getattr(item, "name", "") or "")

    logo_base64 = get_batch_ticket_logo_base64_cached()

    spec_sections = [
        {"label": "Product Name", "value": name},
        {"label": "Item number", "value": sku},
        {"label": "Product Description (physical state, color, odor, etc.)", "value": _s(fps.product_description)},
        {"label": "Color Specification (CV, dye %, color strength, etc.)", "value": _s(fps.color_specification)},
        {"label": "pH", "value": _s(fps.ph)},
        {"label": "Water Activity (aW)", "value": _s(fps.water_activity)},
        {
            "label": "Microbiological Requirements (if micro testing not required, rationale must be provided)",
            "value": _s(fps.microbiological_requirements),
        },
        {
            "label": "Shelf life / Storage Requirements (temperature data). Include Basis for decision and record Shelf-Life Assignment Form (Document No. 5.1.4–03) Shelf-Life Study Log (Document No. 5.1.4–02)",
            "value": _s(fps.shelf_life_storage),
        },
        {"label": "Type of Packaging", "value": _s(fps.packaging_type)},
        {
            "label": "Additional Criteria (physical parameter testing, flavor profile, customer considerations, etc.)",
            "value": _s(fps.additional_criteria),
        },
    ]

    checklist = [
        {"label": "MSDS Created", "checked": bool(fps.msds_created)},
        {"label": "Commercial Spec Created / COA", "checked": bool(fps.commercial_spec_created)},
        {"label": "Label Template Created", "checked": bool(fps.label_template_created)},
        {"label": "Product evaluated for micro growth", "checked": bool(fps.micro_growth_evaluated)},
        {"label": "Product Added to Kosher Letter", "checked": bool(fps.kosher_letter_added)},
        {"label": "Initial HACCP Plan Created", "checked": bool(fps.haccp_plan_created)},
    ]

    formula_version = ""
    formula_rows = []
    try:
        formula = Formula.objects.prefetch_related("ingredients__item").get(finished_good=item)
        formula_version = _s(str(formula.version))
        for ing in formula.ingredients.all():
            iname = _s(getattr(ing.item, "name", "") or "") if ing.item else ""
            try:
                pct = ing.percentage
                pct_s = f"{float(pct):g}" if pct is not None else ""
            except (TypeError, ValueError):
                pct_s = str(ing.percentage) if ing.percentage is not None else ""
            formula_rows.append({"name": iname, "percent": _s(pct_s)})
    except Formula.DoesNotExist:
        pass
    except Exception:
        logger.warning("FPS formula load failed for item %s", getattr(item, "id", None), exc_info=True)

    sig_date = _s(fps.completed_date) if fps.completed_date else ""

    return {
        "logo_base64": logo_base64,
        "product_name": name,
        "item_sku": sku,
        "test_frequency": _s(fps.test_frequency),
        "show_test_frequency": bool(fps.test_frequency),
        "spec_sections": spec_sections,
        "footer_note": FPS_FOOTER_NOTE,
        "checklist_title": "FINISHED PRODUCT SPECIFICATION CHECKLIST",
        "checklist": checklist,
        "processing_requirements": _s(fps.processing_requirements),
        "formula_version": formula_version,
        "formula_rows": formula_rows,
        "has_formula": len(formula_rows) > 0,
        "completed_by_name": _s(fps.completed_by_name),
        "completed_signature": _s(fps.completed_by_signature),
        "completed_date": sig_date,
    }


def generate_fps_pdf_from_html(fps):
    """
    Render FPS HTML template, convert with xhtml2pdf.
    Returns PDF bytes or None on failure.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning("FPS HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None

    try:
        from .models import FinishedProductSpecification

        fps = FinishedProductSpecification.objects.select_related("item").get(pk=fps.pk)
        template_dir = Path(__file__).resolve().parent / "templates" / "fps"
        if not template_dir.is_dir():
            logger.warning("FPS template dir not found: %s", template_dir)
            return None

        env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
        template = env.get_template("finished_product_specification.html")
        context = _build_fps_context(fps)
        html_string = template.render(**context)

        sku = getattr(fps.item, "sku", "") or ""
        out = html_string_to_pdf_bytes(html_string, log_label=f"FPS {sku}".strip() or "FPS PDF")
        if out:
            logger.info("FPS PDF: HTML path succeeded, size=%s", len(out))
        return out
    except Exception as e:
        logger.warning("FPS HTML→PDF failed: %s", e, exc_info=True)
        return None
