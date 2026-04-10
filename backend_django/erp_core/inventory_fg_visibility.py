"""
Finished Good vs Raw inventory visibility for gated product categories.

- distributed_item: FG tab = closed repack outputs only; Raw = everything else (unchanged).
- finished_good with product_category in natural_colors / synthetic_colors / antioxidants:
  FG tab = closed batch outputs (repack or production) only, unless allocation uses allow_prerepack_allocation override.
  Raw tab = receipt / WIP lots for that item until a batch closes.
"""
from __future__ import annotations

GATED_PRODUCT_CATEGORIES = frozenset(
    {'natural_colors', 'synthetic_colors', 'antioxidants'}
)


def item_is_gated_finished_good(item) -> bool:
    return (
        getattr(item, 'item_type', None) == 'finished_good'
        and (getattr(item, 'product_category', None) or '') in GATED_PRODUCT_CATEGORIES
    )


def build_item_meta(sku_items: list) -> dict:
    """Map item_id -> visibility metadata for one SKU group."""
    meta = {}
    for si in sku_items:
        meta[si.id] = {
            'item_type': si.item_type,
            'product_category': si.product_category or '',
        }
    return meta


def filter_lots_finished_good_tab(lots: list, item_meta: dict, repack_output_lot_ids: set, closed_batch_output_lot_ids: set) -> list:
    out = []
    for lot in lots:
        m = item_meta.get(lot.item_id)
        if not m:
            out.append(lot)
            continue
        it = m['item_type']
        if it == 'distributed_item':
            if lot.id in repack_output_lot_ids:
                out.append(lot)
        elif it == 'finished_good':
            cat = m.get('product_category') or ''
            if cat not in GATED_PRODUCT_CATEGORIES:
                out.append(lot)
            elif lot.id in closed_batch_output_lot_ids:
                out.append(lot)
        else:
            out.append(lot)
    return out


def filter_lots_raw_material_tab(lots: list, item_meta: dict, repack_output_lot_ids: set, closed_batch_output_lot_ids: set) -> list:
    out = []
    for lot in lots:
        m = item_meta.get(lot.item_id)
        if not m:
            continue
        it = m['item_type']
        if it == 'raw_material':
            out.append(lot)
        elif it == 'distributed_item':
            if lot.id not in repack_output_lot_ids:
                out.append(lot)
        elif it == 'finished_good':
            cat = m.get('product_category') or ''
            if cat not in GATED_PRODUCT_CATEGORIES:
                continue
            if lot.id not in closed_batch_output_lot_ids:
                out.append(lot)
    return out


def lot_allowed_for_gated_fg_allocation(
    lot, so_item_item, closed_batch_output_lot_ids: set, allow_prerepack_allocation: bool
) -> bool:
    """Gated finished_good line: closed-batch output lot, or explicit allocate override (include raw / pre-repack)."""
    if allow_prerepack_allocation:
        return True
    return lot.id in closed_batch_output_lot_ids


def build_repack_output_vendor_map(candidate_lot_ids) -> dict:
    """
    Map output lot id -> PO vendor name for closed repack batches.

    Repack output lots usually have no po_number (created in-house), so inventory would
    bucket them under Unknown while source material stays under the PO vendor. We infer
    the display vendor from the repack batch's input lots (first input with a resolvable PO vendor).
    """
    if not candidate_lot_ids:
        return {}
    from .models import ProductionBatchOutput, ProductionBatchInput, PurchaseOrder

    ids = list({int(x) for x in candidate_lot_ids})
    out = {}
    for pbo in ProductionBatchOutput.objects.filter(
        lot_id__in=ids,
        batch__batch_type='repack',
        batch__status='closed',
    ).select_related('batch'):
        batch = pbo.batch
        inputs = list(
            ProductionBatchInput.objects.filter(batch=batch).select_related('lot').order_by('id')
        )
        po_nums = [inp.lot.po_number for inp in inputs if inp.lot_id and inp.lot and inp.lot.po_number]
        if not po_nums:
            continue
        pos = {p.po_number: p for p in PurchaseOrder.objects.filter(po_number__in=po_nums)}
        for inp in inputs:
            if not inp.lot or not inp.lot.po_number:
                continue
            po = pos.get(inp.lot.po_number)
            vn = (getattr(po, 'vendor_customer_name', None) or '')
            if isinstance(vn, str):
                vn = vn.strip()
            if vn:
                out[pbo.lot_id] = vn
                break
    return out
