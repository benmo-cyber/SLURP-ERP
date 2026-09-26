"""
Batch ticket PDF via Jinja2 HTML template → xhtml2pdf.
Layout matches the current flowable (BP-13) exactly: same sections, labels, tables, two pages.
"""
from pathlib import Path
import logging
import re

from .html_pdf_common import html_string_to_pdf_bytes
from .mass_quantity import LBS_PER_KG
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

# Alias kept for existing call sites in this module
LB_PER_KG = LBS_PER_KG


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
    ccp_is_na = False
    try:
        from .formula_resolve import formula_for_batch

        # Relabel repack: same source SKU as target — no screen CCP
        if getattr(batch, 'batch_type', None) == 'repack':
            fg_id = getattr(batch, 'finished_good_item_id', None)
            product_ids = set()
            for batch_input in batch.inputs.select_related('lot__item', 'item').all():
                item = (
                    batch_input.resolved_item()
                    if hasattr(batch_input, 'resolved_item')
                    else (batch_input.item or (batch_input.lot.item if batch_input.lot_id else None))
                )
                if not item:
                    continue
                if getattr(item, 'item_type', None) == 'indirect_material' or getattr(
                    item, 'plant_utility', False
                ):
                    continue
                product_ids.add(item.id)
            if fg_id and product_ids == {fg_id}:
                ccp_question = 'N/A — relabel (same container)'
                ccp_is_na = True
            elif getattr(batch, 'critical_control_point_id', None):
                ccp = getattr(batch, 'critical_control_point', None)
                if ccp is None:
                    from .models import CriticalControlPoint

                    ccp = CriticalControlPoint.objects.filter(
                        pk=batch.critical_control_point_id
                    ).first()
                ccp_name = (ccp.name or '').strip() if ccp else ''
                if ccp_name:
                    ccp_question = f'Has {ccp_name} been inspected and installed properly?'

        formula = None if ccp_is_na else formula_for_batch(batch)
        if formula is not None and getattr(formula, "critical_control_point_id", None):
            formula = (
                type(formula).objects.select_related("critical_control_point").get(pk=formula.pk)
            )
        if formula:
            # Prefer stored close notes; fall back to formula QC parameter name.
            if not qc_info.get('parameters'):
                pname = (getattr(formula, 'qc_parameter_name', None) or '').strip()
                if pname:
                    qc_info['parameters'] = pname
            for i in range(1, 7):
                step_text = (getattr(formula, f'mixing_step_{i}', None) or '').strip()
                if step_text:
                    mixing_steps[i - 1] = step_text
            if not ccp_is_na and not getattr(batch, 'critical_control_point_id', None):
                if getattr(formula, 'critical_control_point', None):
                    ccp_name = (formula.critical_control_point.name or '').strip()
                    if ccp_name:
                        ccp_question = f'Has {ccp_name} been inspected and installed properly?'
    except Exception:
        pass

    # Pick list: raw materials only (same as flowable)
    from .pack_display import format_batch_input_packs_note, resolve_pack_size

    pick_rows = []
    for batch_input in batch.inputs.select_related('lot__item', 'lot__pack_size', 'item').prefetch_related(
        'lot__item__pack_sizes', 'item__pack_sizes'
    ).all():
        lot = batch_input.lot
        item = batch_input.resolved_item() if hasattr(batch_input, 'resolved_item') else (lot.item if lot else batch_input.item)
        if not item:
            continue
        if _is_indirect_material(item):
            continue
        vendor = (getattr(item, 'vendor', None) or '').strip() or '—'
        if lot is None or getattr(item, 'plant_utility', False):
            vendor_lot = 'PLANT'
            wildwood_lot = '—'
            packs_note = 'Plant utility'
        else:
            vendor_lot = (lot.vendor_lot_number or lot.lot_number or '—').strip()
            wildwood_lot = (lot.lot_number or '')[:14]
            packs_note = None
        uom = (getattr(item, 'unit_of_measure', None) or 'lbs').strip() or 'lbs'
        qty = batch_input.quantity_used  # stored in item's UoM
        qty_str, uom_out = _mass_line_display(qty, uom, mu)
        try:
            qty_display = float(qty_str.replace(',', ''))
        except (TypeError, ValueError):
            qty_display = float(qty)
        if packs_note is None:
            pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)
            packs_note = format_batch_input_packs_note(
                batch_input,
                qty_display=qty_display,
                qty_uom=uom_out,
                pack_qty=pack_qty,
                pack_uom=pack_uom,
            )
        pick_rows.append({
            'sku': (
                f"Work-in: {(item.sku or '')}"
                if (
                    getattr(item, 'item_type', None) == 'finished_good'
                    and batch.finished_good_item_id
                    and (
                        item.id == batch.finished_good_item_id
                        or (
                            (getattr(item, 'sku_parent_code', None) or '')
                            and (getattr(batch.finished_good_item, 'sku_parent_code', None) or '')
                            and (item.sku_parent_code or '').upper()
                            == (batch.finished_good_item.sku_parent_code or '').upper()
                        )
                    )
                )
                else (item.sku or '')
            )[:24],
            'vendor': vendor[:14],
            'vendor_lot': vendor_lot[:12],
            'qty': qty_str,
            'uom': uom_out[:10],
            'packs_note': packs_note,
            'pick_init': '',
            'prod_init': '',
            'wildwood_lot': wildwood_lot,
        })
    if not pick_rows:
        pick_rows = [{'sku': '', 'vendor': '', 'vendor_lot': '', 'qty': '', 'uom': '', 'packs_note': '', 'pick_init': '', 'prod_init': '', 'wildwood_lot': ''}]

    # Pack off: indirect first, then outputs (same as flowable)
    pack_rows = []
    for batch_input in batch.inputs.select_related('lot__item', 'item').all():
        lot = batch_input.lot
        if lot is None:
            continue
        if not _is_indirect_material(lot.item):
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
        pack_rows.append({
            'packaging': f'OUTPUT - {packaging_desc}',
            'lot': lot.lot_number or '',
            'qty': qty_str,
            'pick_init': '',
            'pack_init': '',
            'amount_unused': '',
            'is_output': True,
        })
    if not pack_rows:
        pack_rows = [{'packaging': '', 'lot': '', 'qty': '', 'pick_init': '', 'pack_init': '', 'amount_unused': ''}]

    def _fmt_closed_qty(val):
        if batch.batch_type == 'repack':
            return _mass_line_display(val, base_unit, mu)
        return _production_totals_display_from_lbs(val, mu, base_unit)

    is_closed = getattr(batch, 'status', None) == 'closed'
    yield_val = ''
    loss_val = ''
    spill_val = ''
    waste_val = ''
    ticket_val = ''
    tq, tu = _fmt_closed_qty(batch.quantity_produced)
    ticket_val = f'{tq} {tu}'
    if is_closed:
        from .make_services import net_yield_native

        net_y = net_yield_native(batch)
        if net_y is not None:
            yq, yu = _fmt_closed_qty(net_y)
            yield_val = f'{yq} {yu}'
        if getattr(batch, 'variance', None) is not None:
            v = float(batch.variance)
            lq, lu = _fmt_closed_qty(abs(v))
            loss_val = f'{"-" if v < 0 else "+"}{lq} {lu}' if v != 0 else f'0 {lu}'
        # Always print recorded spill/waste on closed archive (including 0)
        sq, su = _fmt_closed_qty(float(getattr(batch, 'spills', None) or 0))
        spill_val = f'{sq} {su}'
        wq, wu = _fmt_closed_qty(float(getattr(batch, 'wastes', None) or 0))
        waste_val = f'{wq} {wu}'

    recipe_label_str = ''
    try:
        from .formula_resolve import formula_for_batch, recipe_label

        _f = formula_for_batch(batch)
        recipe_label_str = recipe_label(_f) if _f else ''
    except Exception:
        recipe_label_str = ''

    output_lot_nums = []
    for batch_output in batch.outputs.select_related('lot').all():
        if batch_output.lot_id and batch_output.lot:
            output_lot_nums.append(batch_output.lot.lot_number or str(batch_output.lot_id))
    output_lots_str = ', '.join(output_lot_nums) if output_lot_nums else ''

    closed_summary = {
        'is_closed': is_closed,
        'ticket': ticket_val,
        'actual': yield_val,
        'variance': loss_val,
        'spill': spill_val,
        'waste': waste_val,
        'recipe': recipe_label_str,
        'output_lots': output_lots_str,
        'closed_date': (
            batch.closed_date.strftime('%m/%d/%Y %H:%M')
            if getattr(batch, 'closed_date', None)
            else ''
        ),
        'qc_parameter': (qc_info.get('parameters') or '')[:80],
        'qc_actual': (qc_info.get('actual') or '')[:40],
        'qc_initials': (qc_info.get('initials') or '')[:20],
        'archive_note': (
            'Slurp data archive (unsigned). Signed/initialed paper copy is retained separately.'
            if is_closed
            else ''
        ),
    }

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
        'ccp_is_na': ccp_is_na,
        'qc_info': qc_info,
        'yield_val': yield_val[:24] if yield_val else '',
        'loss_val': loss_val[:24] if loss_val else '',
        'spill_val': spill_val[:20] if spill_val else '',
        'waste_val': waste_val[:20] if waste_val else '',
        'closed_summary': closed_summary,
        'output_lots': output_lots_str,
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
