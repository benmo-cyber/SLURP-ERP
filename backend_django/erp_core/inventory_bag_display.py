"""
Convert roll-based inventory aggregates to bag counts for API responses (inventory table).
Used for raw materials + indirect (packaging) when UOM is ea (rolls) and pack size defines pcs/roll.
"""

from django.db.models import Sum

from .models import ProductionBatchInput, ItemPackSize
from .roll_bag_units import bags_per_roll_from_pack_size


def first_pcs_ea_pack_for_item(display_item):
    """
    First active ItemPackSize that defines bags per roll (pcs or ea).
    Prefer default, then id order — do not use legacy is_default row if it is lbs/gal/kg.
    Uses the item's related manager so prefetch_related('item__pack_sizes') hits cache.
    """
    qs = display_item.pack_sizes.filter(is_active=True).order_by('-is_default', 'id')
    for ps in qs:
        if bags_per_roll_from_pack_size(ps) is not None:
            return ps
    return None


def try_ea_roll_totals_as_bags(
    inventory_table,
    display_item,
    vendor_lots,
    vendor_item,
    lot_sales_allocations,
    use_legacy_on_hold,
    empty_vendor_roll_totals=None,
):
    """
    If UOM is ea (rolls) and we can resolve bags/roll from lot pack size or any pcs/ea ItemPackSize
    on the item, return numeric fields in bags plus display flags.

    empty_vendor_roll_totals: when vendor_lots is empty, dict of roll-based totals from the caller:
      total_quantity, allocated_to_sales, allocated_to_production, on_hold, on_order,
      available, quantity_remaining
    """
    if inventory_table not in ('raw_material', 'indirect_material'):
        return None
    if getattr(display_item, 'unit_of_measure', None) != 'ea':
        return None
    if use_legacy_on_hold:
        return None

    fallback_ps = first_pcs_ea_pack_for_item(display_item)

    def br_from_lot(lot):
        if getattr(lot, 'pack_size_id', None) and lot.pack_size:
            b = bags_per_roll_from_pack_size(lot.pack_size)
            if b is not None:
                return b
        return bags_per_roll_from_pack_size(fallback_ps) if fallback_ps else None

    if not vendor_lots:
        if not empty_vendor_roll_totals or not fallback_ps:
            return None
        bpr = bags_per_roll_from_pack_size(fallback_ps)
        if bpr is None:
            return None
        ev = empty_vendor_roll_totals
        return {
            'total_quantity': float(ev['total_quantity']) * bpr,
            'allocated_to_sales': float(ev['allocated_to_sales']) * bpr,
            'allocated_to_production': float(ev['allocated_to_production']) * bpr,
            'on_hold': float(ev['on_hold']) * bpr,
            'on_order': float(ev['on_order']) * bpr,
            'available': float(ev['available']) * bpr,
            'quantity_remaining': float(ev['quantity_remaining']) * bpr,
            'inventory_display_in_bags': True,
            'inventory_display_unit': 'bags',
        }

    for lot in vendor_lots:
        if br_from_lot(lot) is None:
            return None

    def br(lot):
        return br_from_lot(lot)

    lot_ids = [l.id for l in vendor_lots]
    closed_map = {
        row['lot_id']: float(row['t'] or 0)
        for row in ProductionBatchInput.objects.filter(
            lot_id__in=lot_ids, batch__status='closed'
        ).values('lot_id').annotate(t=Sum('quantity_used'))
    }
    inprog_map = {
        row['lot_id']: float(row['t'] or 0)
        for row in ProductionBatchInput.objects.filter(
            lot_id__in=lot_ids, batch__status='in_progress'
        ).values('lot_id').annotate(t=Sum('quantity_used'))
    }

    received_bags = sum(float(l.quantity) * br(l) for l in vendor_lots)
    consumed_bags = sum(closed_map.get(l.id, 0.0) * br(l) for l in vendor_lots)
    on_order = float(vendor_item.on_order or 0.0) if vendor_item else 0.0
    bpr_order = bags_per_roll_from_pack_size(fallback_ps) if fallback_ps else br(vendor_lots[0])
    if bpr_order is None:
        return None
    on_order_bags = on_order * bpr_order
    total_quantity = received_bags + on_order_bags - consumed_bags

    qty_rem_bags = sum(
        max(
            0.0,
            float(l.quantity_remaining) - float(lot_sales_allocations.get(l.id, 0.0)),
        )
        * br(l)
        for l in vendor_lots
    )
    on_hold_bags = sum(
        float(getattr(l, 'quantity_on_hold', 0.0) or 0.0) * br(l) for l in vendor_lots
    )
    allocated_to_production_bags = sum(
        inprog_map.get(l.id, 0.0) * br(l) for l in vendor_lots
    )
    allocated_to_sales_bags = sum(
        float(lot_sales_allocations.get(l.id, 0.0)) * br(l) for l in vendor_lots
    )
    available = max(0.0, qty_rem_bags - on_hold_bags - allocated_to_production_bags)

    return {
        'total_quantity': total_quantity,
        'allocated_to_sales': allocated_to_sales_bags,
        'allocated_to_production': allocated_to_production_bags,
        'on_hold': on_hold_bags,
        'on_order': on_order_bags,
        'available': available,
        'quantity_remaining': qty_rem_bags,
        'inventory_display_in_bags': True,
        'inventory_display_unit': 'bags',
    }


def bags_per_roll_for_lot_instance(lot):
    """
    Bags per inventory roll (ea) for lot API payloads — lot pack size or first pcs/ea ItemPackSize on item.
    """
    item = getattr(lot, 'item', None)
    if item is None or getattr(item, 'unit_of_measure', None) != 'ea':
        return None
    if getattr(lot, 'pack_size_id', None) and lot.pack_size:
        b = bags_per_roll_from_pack_size(lot.pack_size)
        if b is not None:
            return b
    fb = first_pcs_ea_pack_for_item(item)
    if fb is None:
        return None
    return bags_per_roll_from_pack_size(fb)
