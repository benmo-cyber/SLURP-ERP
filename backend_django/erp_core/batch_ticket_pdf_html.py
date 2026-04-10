"""
Batch ticket PDF via Jinja2 HTML template → xhtml2pdf.
Layout matches the current flowable (BP-13) exactly: same sections, labels, tables, two pages.
"""
from pathlib import Path
import logging
import re

from .html_pdf_common import html_string_to_pdf_bytes
from .pdf_generator import get_logo_base64_cached

logger = logging.getLogger(__name__)

CONFIDENTIALITY_FOOTER = (
    "This document contains confidential and proprietary information intended solely for the recipient. "
    "By accepting this document, you agree to maintain the confidentiality of its contents and not to disclose, "
    "distribute, or use any information herein for purposes other than those expressly authorized. "
    "Unauthorized use or disclosure may result in legal action. If you are not the intended recipient, "
    "please notify the sender immediately and delete this document from your system."
)
BATCH_TICKET_UPDATED = "Batch Ticket – Updated 02/06/2026 (GDM) – Reviewed by GM – Effective Date 02/06/2026 (BP-13)"

LB_PER_KG = 2.20462


def _normalize_mass_unit_param(value):
    """Map query param / saved field to native | lbs | kg."""
    if value is None:
        return 'native'
    v = str(value).strip().lower()
    if not v:
        return 'native'
    if v in ('lb', 'lbs', 'pound', 'pounds'):
        return 'lbs'
    if v in ('kg', 'kgs', 'kilogram', 'kilograms'):
        return 'kg'
    if v in ('native', 'item', 'items', 'original'):
        return 'native'
    return 'native'


def _format_qty_display_number(qty):
    q = float(qty)
    if abs(q - round(q)) <= 0.01:
        return str(int(round(q)))
    return f'{q:.2f}'


def _mass_line_display(qty, native_uom, mass_unit):
    """
    Match production UI: convert mass between lbs/kg; leave count (ea) unchanged.
    Returns (qty_str, uom_label).
    """
    u = (native_uom or 'lbs').strip().lower()
    if u in ('ea', 'each', 'e.a.'):
        return _format_qty_display_number(qty), 'ea'
    if mass_unit == 'native':
        label = 'lbs' if u in ('lb', 'lbs') else ('kg' if u == 'kg' else (native_uom or 'lbs')[:10])
        return _format_qty_display_number(qty), label[:10]
    q = float(qty)
    if mass_unit == 'lbs':
        if u == 'kg':
            return _format_qty_display_number(q * LB_PER_KG), 'lbs'
        return _format_qty_display_number(q), 'lbs'
    # kg
    if u in ('lbs', 'lb'):
        return _format_qty_display_number(q / LB_PER_KG), 'kg'
    return _format_qty_display_number(q), 'kg'


def _production_totals_display_from_lbs(qty_lbs, mass_unit, fg_uom):
    """
    quantity_produced / quantity_actual / variance / wastes / spills are stored in lbs;
    wastes & spills explain shortfall vs ticket; they do not reduce quantity_actual on the output lot
    for production batches (not repack).
    """
    fg = (fg_uom or 'lbs').strip().lower()
    q = float(qty_lbs)
    if mass_unit == 'native':
        if fg in ('kg',):
            return _format_qty_display_number(q / LB_PER_KG), 'kg'
        if fg in ('lbs', 'lb', 'ea'):
            return _format_qty_display_number(q), 'lbs' if fg != 'lb' else 'lbs'
        return _format_qty_display_number(q), (fg_uom or 'lbs')[:10]
    if mass_unit == 'lbs':
        return _format_qty_display_number(q), 'lbs'
    return _format_qty_display_number(q / LB_PER_KG), 'kg'


def _repack_header_display(qty, fg_uom, mass_unit):
    """Repack: quantity_produced is already in finished good native UoM."""
    return _mass_line_display(qty, fg_uom or 'lbs', mass_unit)


def _is_indirect_material(item):
    if item is None:
        return False
    t = (getattr(item, 'item_type', None) or '').strip().lower()
    return t == 'indirect_material' or 'indirect' in t


def _build_batch_ticket_context(batch, mass_unit='native'):
    """
    Build template context from batch. Matches data used by flowable in batch_ticket_pdf.py.

    mass_unit: 'native' (each line uses item / FG UoM as stored), 'lbs', or 'kg' — same idea as
    the production UI display toggle so PDF pick list and batch totals can match the screen.
    """
    if not getattr(batch, 'finished_good_item', None):
        return None
    fg = batch.finished_good_item
    mu = _normalize_mass_unit_param(mass_unit)
    base_unit = fg.unit_of_measure or 'lbs'

    if batch.batch_type == 'repack':
        bqs, bu = _repack_header_display(batch.quantity_produced, base_unit, mu)
        batch_size_str = f'{bqs} {bu}'
    else:
        bqs, bu = _production_totals_display_from_lbs(batch.quantity_produced, mu, base_unit)
        batch_size_str = f'{bqs} {bu}'
    batch_size_str = batch_size_str[:20]

    pack_size_str = ''
    if getattr(fg, 'pack_size', None) is not None:
        ps_u = (base_unit or 'lbs').strip().lower()
        pv = float(fg.pack_size)
        if mu == 'lbs' and ps_u == 'kg':
            pv = pv * LB_PER_KG
            ps_u = 'lbs'
        elif mu == 'kg' and ps_u in ('lbs', 'lb'):
            pv = pv / LB_PER_KG
            ps_u = 'kg'
        pack_size_str = f'{_format_qty_display_number(pv)} {ps_u}'
    elif getattr(fg, 'pack_sizes', None) and fg.pack_sizes.filter(is_active=True).exists():
        ps = fg.pack_sizes.filter(is_active=True).first()
        pu = (ps.pack_size_unit or 'lbs').strip().lower()
        pv = float(ps.pack_size)
        if mu == 'lbs' and pu == 'kg':
            pv = pv * LB_PER_KG
            pu = 'lbs'
        elif mu == 'kg' and pu in ('lbs', 'lb'):
            pv = pv / LB_PER_KG
            pu = 'kg'
        pack_size_str = f'{_format_qty_display_number(pv)} {pu}'

    prod_date_str = batch.production_date.strftime('%m/%d/%Y') if batch.production_date else ''

    campaign_lot_code = ''
    camp = getattr(batch, 'campaign', None)
    if camp is not None and getattr(camp, 'campaign_code', None):
        campaign_lot_code = (camp.campaign_code or '')[:48]

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
        qty_str, uom_out = _mass_line_display(qty, uom, mu)
        pick_rows.append({
            'sku': (item.sku or '')[:18],
            'vendor': vendor[:14],
            'vendor_lot': vendor_lot[:12],
            'qty': qty_str,
            'uom': uom_out[:10],
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
        out_u = (getattr(item, 'unit_of_measure', None) or base_unit or 'lbs').strip() or 'lbs'
        if batch.batch_type == 'repack':
            oqs, ou = _mass_line_display(batch_output.quantity_produced, out_u, mu)
            qty_str = f'{oqs} {ou}'
        else:
            oqs, ou = _mass_line_display(batch_output.quantity_produced, 'lbs', mu)
            qty_str = f'{oqs} {ou}'
        packaging_desc = (getattr(item, 'description', None) or item.name or item.sku or '').strip() or (item.name or item.sku or '')
        pack_rows.append({'packaging': packaging_desc, 'lot': lot.lot_number or '', 'qty': qty_str, 'pick_init': '', 'pack_init': '', 'amount_unused': ''})
    if not pack_rows:
        pack_rows = [{'packaging': '', 'lot': '', 'qty': '', 'pick_init': '', 'pack_init': '', 'amount_unused': ''}]

    def _fmt_closed_qty(val):
        if batch.batch_type == 'repack':
            return _mass_line_display(val, base_unit, mu)
        return _production_totals_display_from_lbs(val, mu, base_unit)

    yield_val = ''
    if getattr(batch, 'status', None) == 'closed' and getattr(batch, 'quantity_actual', None):
        yq, yu = _fmt_closed_qty(batch.quantity_actual)
        yield_val = f'{yq} {yu}'
    loss_val = ''
    if getattr(batch, 'status', None) == 'closed' and getattr(batch, 'variance', None) is not None:
        v = float(batch.variance)
        lq, lu = _fmt_closed_qty(abs(v))
        loss_val = f'{"-" if v < 0 else ""}{lq} {lu}'
    spill_val = ''
    if getattr(batch, 'spills', None):
        sq, su = _fmt_closed_qty(batch.spills)
        spill_val = f'{sq} {su}'
    waste_val = ''
    if getattr(batch, 'wastes', None):
        wq, wu = _fmt_closed_qty(batch.wastes)
        waste_val = f'{wq} {wu}'

    logo_base64 = get_logo_base64_cached()

    return {
        'product_id': str(fg.id),
        'sku': (fg.sku or '')[:30],
        'batch_number': (batch.batch_number or '')[:24],
        'campaign_lot_code': campaign_lot_code,
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


def generate_batch_ticket_pdf_from_html(batch, mass_unit=None):
    """
    Render batch ticket HTML template with Jinja2, convert to PDF with xhtml2pdf.
    Resolution order (so PDF matches the unit chosen when the batch was created):
    1) batch.batch_ticket_mass_unit if set (lbs / kg / native)
    2) optional mass_unit query override (legacy / batches with no saved preference)
    3) native (each line in its item UoM)
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError as e:
        logger.warning("Batch ticket HTML→PDF requires jinja2 and xhtml2pdf: %s", e)
        return None, None

    saved = getattr(batch, 'batch_ticket_mass_unit', None)
    if saved is not None and str(saved).strip():
        eff_mu = _normalize_mass_unit_param(saved)
    elif mass_unit is not None and str(mass_unit).strip():
        eff_mu = _normalize_mass_unit_param(mass_unit)
    else:
        eff_mu = 'native'

    context = _build_batch_ticket_context(batch, mass_unit=eff_mu)
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

        bn = (getattr(batch, "batch_number", None) or "") or ""
        pdf_bytes = html_string_to_pdf_bytes(html_string, log_label=f"Batch ticket {bn}".strip() or "Batch ticket PDF")
        if not pdf_bytes:
            return None, None
        status_prefix = getattr(batch, 'status', 'draft').replace('_', '-')
        filename = f"{status_prefix}({batch.batch_number}).pdf"
        logger.info("Batch ticket PDF: HTML path succeeded, size=%s", len(pdf_bytes))
        return pdf_bytes, filename
    except Exception as e:
        logger.warning("Batch ticket HTML→PDF failed: %s", e, exc_info=True)
        return None, None
