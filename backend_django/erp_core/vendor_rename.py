"""When Vendor.name changes, denormalized name strings elsewhere must be updated too."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def cascade_vendor_name_change(old_name: str, new_name: str) -> dict[str, int]:
    """
    Update all tables that store vendor name as plain text (not FK to Vendor).

    Call this after Vendor.name changes from old_name to new_name.
    """
    from erp_core.models import (
        AccountsPayable,
        CostMaster,
        Item,
        OrphanedInventory,
        OrphanedPurchaseOrderItem,
        PurchaseOrder,
        VendorPricing,
    )

    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return {}

    counts: dict[str, int] = {}

    n = Item.objects.filter(vendor=old_name).update(vendor=new_name)
    counts["items"] = n

    n = CostMaster.objects.filter(vendor=old_name).update(vendor=new_name)
    counts["cost_master"] = n

    n = VendorPricing.objects.filter(vendor_name=old_name).update(vendor_name=new_name)
    counts["vendor_pricing"] = n

    n = AccountsPayable.objects.filter(vendor_name=old_name).update(vendor_name=new_name)
    counts["accounts_payable"] = n

    n = PurchaseOrder.objects.filter(po_type="vendor", vendor_customer_name=old_name).update(
        vendor_customer_name=new_name
    )
    counts["purchase_orders"] = n

    n = OrphanedInventory.objects.filter(original_item_vendor=old_name).update(
        original_item_vendor=new_name
    )
    counts["orphaned_inventory"] = n

    n = OrphanedPurchaseOrderItem.objects.filter(original_item_vendor=old_name).update(
        original_item_vendor=new_name
    )
    counts["orphaned_po_items"] = n

    logger.info("Vendor name cascade %r -> %r: %s", old_name, new_name, counts)
    return counts
