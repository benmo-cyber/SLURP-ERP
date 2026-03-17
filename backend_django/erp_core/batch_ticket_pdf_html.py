"""
Batch ticket PDF via Jinja2 HTML template → xhtml2pdf.
Layout matches the current flowable (BP-13) exactly: same sections, labels, tables, two pages.
"""
from pathlib import Path
import base64
import logging
import re
from io import BytesIO

logger = logging.getLogger(__name__)

CONFIDENTIALITY_FOOTER = (
    "This document contains confidential and proprietary information intended solely for the recipient. "
    "By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, "
    "distribute, or use any information herein for purposes other than those expressly authorized. "
    "Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, "
    "please notify the sender immediately and delete this document from your system."
)
BATCH_TICKET_UPDATED = "Batch Ticket – Updated 02/06/2026 (GDM) – Reviewed by GM – Effective Date 02/06/2026 (BP-13)"


def _is_indirect_material(item):
    if item is None:
        return False
    t = (getattr(item, 'item_type', None) or '').strip().lower()
    return t == 'indirect_material' or 'indirect' in t


def _build_batch_ticket_context(batch):
    """Build template context from batch. Matches data used by flowable in batch_ticket_pdf.py."""
    if not getattr(batch, 'finished_good_item', None):
        return None
    fg = batch.finished_good_item
    base_unit = fg.unit_of_measure or 'lbs'

    def convert_from_lbs_to_base(quantity_in_lbs):
        if base_unit in ('lbs', 'ea'):
            return quantity_in_lbs
        if base_unit == 'kg':
            return quantity_in_lbs / 2.20462
        return quantity_in_lbs

    if batch.batch_type == 'repack':
        quantity_produced_display = batch.quantity_produced
    else:
        quantity_produced_display = convert_from_lbs_to_base(batch.quantity_produced)

    if abs(quantity_produced_display - round(quantity_produced_display)) <= 0.02:
        batch_size_str = f"{int(round(quantity_produced_display))} {base_unit}"
    else:
        batch_size_str = f"{quantity_produced_display:.2f} {base_unit}"
    batch_size_str = batch_size_str[:20]

    pack_size_str = ''
    if getattr(fg, 'pack_size', None) is not None:
        pack_size_str = f"{fg.pack_size} {base_unit}"
    elif getattr(fg, 'pack_sizes', None) and fg.pack_sizes.filter(is_active=True).exists():
        ps = fg.pack_sizes.filter(is_active=True).first()
        pack_size_str = f"{ps.pack_size} {ps.pack_size_unit}"

    prod_date_str = batch.production_date.strftime('%m/%d/%Y') if batch.production_date else ''

    qc_info = {}
    if getattr(batch, 'notes', None):
        for key, pattern in [
            ('parameters', r'QC Parameters:\s*(.+?)(?:\n|QC Actual:|$)'),
            ('actual', r'QC Actual:\s*(.+?)(?:\n|QC Initials:|$)'),
            ('initials', r'QC Initials:\s*(.+?)(?:\n|$)'),
        ]:
            m = re.search(pattern, batch.notes, re.IGNORECASE | re.DOTALL)
            if m:
                qc_info[key] = m.group(1).strip()

    mixing_steps = ['', '', '', '', '', '']
    ccp_question = 'Has 20 mesh screen been inspected and installed properly?'  # default
    try:
        from .models import Formula
        formula = getattr(fg, 'formula', None) or Formula.objects.select_related('critical_control_point').filter(finished_good=fg).first()
        if formula:
            for i in range(1, 7):
                step_text = (getattr(formula, f'mixing_step_{i}', None) or '').strip()
                if step_text:
                    mixing_steps[i - 1] = step_text
            if getattr(formula, 'critical_control_point', None):
                ccp_name = (formula.critical_control_point.name or '').strip()
                if ccp_name:
                    ccp_question = f'Has {ccp_name} been inspected and installed properly?'
    except Exception:
        pass

    # Pick list: raw materials only (same as flowable)
    pick_rows = []
    for batch_input in batch.inputs.select_related('lot__item').all():
        lot = batch_input.lot
        item = lot.item
        if _is_indirect_material(item):
            continue
        vendor = (getattr(item, 'vendor', None) or '').strip() or '—'
        vendor_lot = (lot.vendor_lot_number or lot.lot_number or '—').strip()
        uom = (getattr(item, 'unit_of_measure', None) or 'lbs').strip() or 'lbs'
        qty = batch_input.quantity_used  # stored in item's UoM
        qty_str = f"{int(round(qty))}" if abs(qty - round(qty)) <= 0.01 else f"{qty:.2f}"
        pick_rows.append({
            'sku': (item.sku or '')[:18],
            'vendor': vendor[:14],
            'vendor_lot': vendor_lot[:12],
            'qty': qty_str,
            'uom': uom[:10],
            'pick_init': '',
            'prod_init': '',
            'wildwood_lot': (lot.lot_number or '')[:14],
        })
    if not pick_rows:
        pick_rows = [{'sku': '', 'vendor': '', 'vendor_lot': '', 'qty': '', 'uom': '', 'pick_init': '', 'prod_init': '', 'wildwood_lot': ''}]

    # Pack off: indirect first, then outputs (same as flowable)
    pack_rows = []
    for batch_input in batch.inputs.select_related('lot__item').all():
        if not _is_indirect_material(batch_input.lot.item):
            continue
        item = batch_input.lot.item
        lot = batch_input.lot
        qty_str = f"{int(batch_input.quantity_used)}" if batch_input.quantity_used == int(batch_input.quantity_used) else f"{batch_input.quantity_used:.2f}"
        packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
        pack_rows.append({'packaging': packaging_desc, 'lot': lot.lot_number or '', 'qty': f"{qty_str} EA", 'pick_init': '', 'pack_init': '', 'amount_unused': ''})
    for batch_output in batch.outputs.select_related('lot__item').all():
        lot = batch_output.lot
        item = lot.item
        qty = batch_output.quantity_produced
        if batch.batch_type != 'repack':
            qty = convert_from_lbs_to_base(qty)
        qty_str = f"{qty:.2f}" if qty != int(qty) else str(int(qty))
        packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
        pack_rows.append({'packaging': packaging_desc, 'lot': lot.lot_number or '', 'qty': qty_str, 'pick_init': '', 'pack_init': '', 'amount_unused': ''})
    if not pack_rows:
        pack_rows = [{'packaging': '', 'lot': '', 'qty': '', 'pick_init': '', 'pack_init': '', 'amount_unused': ''}]

    yield_val = ''
    if getattr(batch, 'status', None) == 'closed' and getattr(batch, 'quantity_actual', None):
        yield_val = f"{convert_from_lbs_to_base(batch.quantity_actual):.2f} {base_unit}"
    loss_val = ''
    if getattr(batch, 'status', None) == 'closed' and getattr(batch, 'variance', None) is not None:
        loss_val = f"{convert_from_lbs_to_base(batch.variance):.2f} {base_unit}"
    spill_val = f"{convert_from_lbs_to_base(batch.spills):.2f}" if getattr(batch, 'spills', None) else ''
    waste_val = f"{convert_from_lbs_to_base(batch.wastes):.2f}" if getattr(batch, 'wastes', None) else ''

    logo_base64 = ''
    try:
        from .pdf_generator import get_logo_path
        logo_path = get_logo_path()
        if logo_path and Path(logo_path).exists():
            with open(logo_path, 'rb') as f:
                logo_base64 = base64.b64encode(f.read()).decode('ascii')
    except Exception:
        pass

    return {
        'product_id': str(fg.id),
        'sku': (fg.sku or '')[:30],
        'batch_number': (batch.batch_number or '')[:24],
        'batch_size': batch_size_str,
        'pack_size': (pack_size_str or '')[:20],
        'prod_date': (prod_date_str or '')[:16],
        'pick_rows': pick_rows,
        'pack_rows': pack_rows,
        'mixing_steps': mixing_steps,
        'ccp_question': ccp_question,
        'qc_info': qc_info,
        'yield_val': yield_val[:20] if yield_val else '',
        'loss_val': loss_val[:20] if loss_val else '',
        'spill_val': spill_val[:12] if spill_val else '',
        'waste_val': waste_val[:12] if waste_val else '',
        'confidentiality': CONFIDENTIALITY_FOOTER,
        'batch_ticket_updated': BATCH_TICKET_UPDATED,
        'logo_base64': logo_base64,
    }


def generate_batch_ticket_pdf_from_html(batch):
    """
    Render batch ticket HTML template with Jinja2, convert to PDF with xhtml2pdf.
    Returns (pdf_bytes, filename) or (None, None) on failure.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from xhtml2pdf import pisa
    except ImportError as e:
        logger.warning("Batch ticket HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None, None

    context = _build_batch_ticket_context(batch)
    if not context:
        return None, None

    try:
        template_dir = Path(__file__).resolve().parent / "templates" / "batch_ticket"
        if not template_dir.is_dir():
            logger.warning("Batch ticket template dir not found: %s", template_dir)
            return None, None

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("batch_ticket.html")
        html_string = template.render(**context)

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(html_string, dest=pdf_buffer, encoding="utf-8")
        if getattr(result, "err", 1) != 0:
            logger.warning("Batch ticket xhtml2pdf errors: err=%s", getattr(result, "err", None))
            return None, None
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.getvalue()
        status_prefix = getattr(batch, 'status', 'draft').replace('_', '-')
        filename = f"{status_prefix}({batch.batch_number}).pdf"
        logger.info("Batch ticket PDF: HTML path succeeded, size=%s", len(pdf_bytes))
        return pdf_bytes, filename
    except Exception as e:
        logger.warning("Batch ticket HTML→PDF failed: %s", e, exc_info=True)
        return None, None
