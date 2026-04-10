"""
Roll/bag math for inventory and costing (mirrors frontend src/utils/rollBagUnits.ts).

Inventory for many packaging SKUs is stored in rolls (item UOM = ea). ItemPackSize
with unit pcs or ea gives bags per roll; actual bags on hand = rolls * bags_per_roll.
"""


def bags_per_roll_from_pack_size(pack):
    """Return bags per one inventory roll, or None if pack does not define that."""
    if pack is None:
        return None
    try:
        v = float(pack.pack_size)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    u = (getattr(pack, 'pack_size_unit', None) or '').strip().lower()
    # Some rows omit unit; for roll stock + pack master numeric, treat as pcs/bags per roll
    if not u:
        u = 'pcs'
    if u in ('pcs', 'pc', 'ea', 'piece', 'pieces'):
        return v
    return None


def rolls_to_bags(rolls, bags_per_roll):
    return round(float(rolls) * float(bags_per_roll) * 1000) / 1000


def bags_to_rolls(bags, bags_per_roll):
    if bags_per_roll <= 0:
        return 0.0
    return round((float(bags) / float(bags_per_roll)) * 1e6) / 1e6


def unit_cost_per_bag(price_per_roll, bags_per_roll):
    """When price is per roll and pack master gives bags/roll, cost per bag."""
    if bags_per_roll is None or bags_per_roll <= 0:
        return None
    try:
        pr = float(price_per_roll)
    except (TypeError, ValueError):
        return None
    return pr / float(bags_per_roll)
