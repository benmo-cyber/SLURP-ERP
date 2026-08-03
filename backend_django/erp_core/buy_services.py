"""
Shared BUY-flow services: Create PO → Issue → Check-In → Reverse check-in.

Used by DRF ViewSets and slurp_ui Django templates so business rules live in one place.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from django.db import transaction
from django.utils import timezone

from .mass_quantity import convert_mass_uom, normalize_quantity_by_uom
from .models import (
    CheckInLog,
    InventoryTransaction,
    Item,
    ItemPackSize,
    Lot,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    Vendor,
)

logger = logging.getLogger(__name__)


class BuyFlowError(Exception):
    """User-facing BUY flow error with optional HTTP-ish status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _po_by_number(po_number: str) -> PurchaseOrder | None:
    return (
        PurchaseOrder.objects.filter(po_number=po_number)
        .order_by("-revision_number", "-id")
        .first()
    )


def create_purchase_order(user, data: dict) -> PurchaseOrder:
    """
    Create a draft vendor PO with lines.

    ``data`` matches the DRF create payload (vendor_id, items[{item_id,quantity,unit_cost,order_uom}], …).
    """
    from .serializers import PurchaseOrderSerializer
    from .views import (
        apply_sales_order_ship_to_to_purchase_order,
        generate_po_number,
        log_purchase_order_action,
    )

    payload = deepcopy(data) if data is not None else {}
    # QueryDict / immutable → plain dict of lists/scalars
    if hasattr(payload, "lists"):
        payload = {k: (v[0] if len(v) == 1 else v) for k, v in payload.lists()}

    if not getattr(user, "is_staff", False):
        payload.pop("order_date", None)
        payload.pop("issue_date", None)

    items_data = payload.pop("items", []) or []
    if isinstance(items_data, dict):
        items_data = [items_data]

    vendor_id = payload.pop("vendor_id", None)
    if vendor_id in (None, ""):
        raise BuyFlowError("Vendor is required.")
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except (Vendor.DoesNotExist, ValueError, TypeError) as e:
        raise BuyFlowError(f"Vendor with id {vendor_id} not found") from e

    payload["vendor_customer_name"] = vendor.name
    payload["vendor_customer_id"] = str(vendor.id)
    payload.setdefault("status", "draft")
    payload.setdefault("po_type", "vendor")

    if not payload.get("po_number"):
        payload["po_number"] = generate_po_number()

    if not payload.get("required_date") and payload.get("expected_delivery_date"):
        payload["required_date"] = payload["expected_delivery_date"]
    if not payload.get("expected_delivery_date") and payload.get("required_date"):
        payload["expected_delivery_date"] = payload["required_date"]

    # Defaults for ship-to when omitted
    payload.setdefault("ship_to_name", "Wildwood Ingredients, LLC")
    payload.setdefault("ship_to_address", "6431 Michels Dr.")
    payload.setdefault("ship_to_city", "Washington")
    payload.setdefault("ship_to_state", "MO")
    payload.setdefault("ship_to_zip", "63090")
    payload.setdefault("ship_to_country", "USA")

    notify_ids = payload.pop("notify_party_contact_ids", None)

    if not items_data:
        raise BuyFlowError("At least one line item is required.")

    try:
        serializer = PurchaseOrderSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        purchase_order = serializer.save()
    except Exception as e:
        # DRF ValidationError has detail; keep message readable
        detail = getattr(e, "detail", None)
        raise BuyFlowError(f"Failed to create purchase order: {detail or e}") from e

    if notify_ids is not None:
        try:
            purchase_order.notify_party_contacts.set(notify_ids)
        except Exception:
            pass

    if purchase_order.drop_ship and purchase_order.fulfillment_sales_order_id:
        try:
            so = SalesOrder.objects.select_related("ship_to_location", "customer").get(
                pk=purchase_order.fulfillment_sales_order_id
            )
            apply_sales_order_ship_to_to_purchase_order(purchase_order, so)
            purchase_order.save(
                update_fields=[
                    "ship_to_name",
                    "ship_to_address",
                    "ship_to_city",
                    "ship_to_state",
                    "ship_to_zip",
                    "ship_to_country",
                ]
            )
        except SalesOrder.DoesNotExist:
            pass

    try:
        with transaction.atomic():
            for item_data in items_data:
                item_id = item_data.get("item_id")
                if not item_id:
                    raise BuyFlowError(f"item_id is required for item: {item_data}")
                unit_price = item_data.get("unit_cost", item_data.get("unit_price", 0)) or 0
                quantity_ordered = float(
                    item_data.get("quantity", item_data.get("quantity_ordered", 0)) or 0
                )
                if quantity_ordered <= 0:
                    raise BuyFlowError(f"quantity must be greater than 0, got: {quantity_ordered}")
                PurchaseOrderItem.objects.create(
                    purchase_order=purchase_order,
                    item_id=item_id,
                    quantity_ordered=quantity_ordered,
                    unit_price=float(unit_price),
                    order_uom=(item_data.get("order_uom") or "").strip() or None,
                    notes=item_data.get("notes", "") or "",
                )
            purchase_order.calculate_totals()
            log_purchase_order_action(purchase_order, "created", notes="Purchase order created")
    except BuyFlowError:
        purchase_order.delete()
        raise
    except Exception as e:
        purchase_order.delete()
        raise BuyFlowError(f"Failed to create purchase order item: {e}") from e

    return purchase_order


def issue_purchase_order(purchase_order: PurchaseOrder, user, issue_date=None) -> PurchaseOrder:
    """Issue a draft PO: status=issued, on_order++, email PDF (best effort)."""
    from .po_pdf_html import generate_po_pdf_from_html
    from .email_service import send_purchase_order_email
    from .views import _parse_staff_datetime, log_purchase_order_action

    if purchase_order.status != "draft":
        raise BuyFlowError(
            f"Purchase order must be in draft status to issue. Current status: {purchase_order.status}"
        )

    if issue_date is not None and str(issue_date).strip() != "":
        if not getattr(user, "is_staff", False):
            raise BuyFlowError(
                "Only staff can set a custom issue date (God mode).",
                status_code=403,
            )
        parsed = _parse_staff_datetime(issue_date)
        if parsed is None:
            raise BuyFlowError("Invalid issue_date. Use YYYY-MM-DD or ISO datetime.")
        purchase_order.order_date = parsed

    purchase_order.status = "issued"
    purchase_order.save()
    log_purchase_order_action(purchase_order, "updated", notes="Purchase order issued")

    if not purchase_order.drop_ship:
        for po_item in purchase_order.items.select_related("item"):
            if po_item.item:
                item = po_item.item
                item.on_order = (item.on_order or 0) + po_item.quantity_ordered
                item.save(update_fields=["on_order"])

    try:
        pdf_content = generate_po_pdf_from_html(purchase_order)
        if pdf_content:
            send_purchase_order_email(purchase_order, pdf_content)
    except Exception as e:
        logger.error("Failed to send purchase order email: %s", e)

    return purchase_order


def check_in_lot(user, data: dict) -> Lot:
    """
    Receive inventory against an issued PO (or standalone).

    Enforces attestations, raw-material vendor lot, drop-ship block, and
    over-receipt vs PO line remaining. Converts entry_uom → item UoM when given.
    """
    from .serializers import LotSerializer
    from .views import (
        create_ap_entry_from_po,
        generate_lot_number,
        log_lot_transaction,
        log_purchase_order_action,
        _parse_staff_datetime,
    )

    payload = dict(data or {})
    item_id = payload.get("item_id")
    if not item_id:
        raise BuyFlowError("item_id is required.")
    try:
        item = Item.objects.get(id=item_id)
    except Item.DoesNotExist as e:
        raise BuyFlowError(f"Item {item_id} not found") from e

    # Attestations (were frontend-only)
    coa = _as_bool(payload.get("coa"))
    prod_free_pests = _as_bool(payload.get("prod_free_pests"))
    carrier_free_pests = _as_bool(payload.get("carrier_free_pests"))
    shipment_accepted = _as_bool(payload.get("shipment_accepted"))
    initials = (payload.get("initials") or "").strip()
    if not (coa and prod_free_pests and carrier_free_pests and shipment_accepted):
        raise BuyFlowError(
            "All check-in attestations are required (COA, product free of pests, "
            "carrier free of pests, shipment accepted)."
        )
    if not initials:
        raise BuyFlowError("Initials are required for check-in.")

    manual_lot = (payload.get("lot_number") or "").strip() or None
    if manual_lot:
        if not getattr(user, "is_staff", False):
            manual_lot = None
        elif Lot.objects.filter(lot_number=manual_lot).exists():
            raise BuyFlowError(
                f'Lot number "{manual_lot}" already exists. Use a different number or leave blank.'
            )

    if item.item_type == "raw_material":
        vendor_lot_number = (payload.get("vendor_lot_number") or "").strip()
        if not vendor_lot_number:
            raise BuyFlowError("Vendor lot number is required for raw materials")
        payload["vendor_lot_number"] = vendor_lot_number

    po_number_raw = (payload.get("po_number") or "").strip()
    po = _po_by_number(po_number_raw) if po_number_raw else None
    if po_number_raw and po and po.drop_ship:
        raise BuyFlowError(
            f"PO {po.po_number} is drop ship. Product goes direct to the customer — "
            "do not check in to inventory."
        )
    if po and po.status not in ("issued", "received"):
        raise BuyFlowError(
            f"PO {po.po_number} must be issued to check in (current status: {po.status})."
        )

    # Quantity: convert entry UoM → item native UoM
    try:
        qty_entry = float(payload.get("quantity") or 0)
    except (TypeError, ValueError) as e:
        raise BuyFlowError("Invalid quantity.") from e
    if qty_entry <= 0:
        raise BuyFlowError("Quantity must be greater than 0.")

    entry_uom = (payload.get("entry_uom") or payload.get("quantity_unit") or "").strip().lower()
    item_uom = (item.unit_of_measure or "lbs").lower()
    if entry_uom and entry_uom != item_uom:
        try:
            qty_native = convert_mass_uom(qty_entry, entry_uom, item_uom)
        except ValueError as e:
            raise BuyFlowError(str(e)) from e
    else:
        qty_native = normalize_quantity_by_uom(qty_entry, item_uom)

    # Over-receipt guard vs PO line
    if po:
        po_item = next((li for li in po.items.all() if li.item_id == item.id), None)
        if po_item is None:
            raise BuyFlowError(f"Item {item.sku} is not on PO {po.po_number}.")
        remaining = float(po_item.quantity_ordered or 0) - float(po_item.quantity_received or 0)
        if qty_native > remaining + 0.01:
            raise BuyFlowError(
                f"Quantity {qty_native} {item_uom} exceeds remaining PO qty "
                f"{remaining:.2f} {item_uom} for {item.sku}."
            )

    lot_status = payload.get("status") or "accepted"
    lot_number = manual_lot or generate_lot_number()

    # Dates
    received_raw = payload.get("received_date")
    if received_raw and str(received_raw).strip():
        if not getattr(user, "is_staff", False):
            # Non-staff: still allow today/past via form; refuse future beyond today handled by UI
            pass
        received_dt = _parse_staff_datetime(received_raw) or timezone.now()
    else:
        received_dt = timezone.now()

    serializer_data = {
        "item_id": item.id,
        "quantity": qty_native,
        "received_date": received_dt.isoformat(),
        "status": lot_status,
        "lot_number": lot_number,
        "po_number": po.po_number if po else (po_number_raw or None),
        "vendor_lot_number": payload.get("vendor_lot_number") or "",
        "short_reason": payload.get("short_reason") or None,
        "freight_actual": payload.get("freight_actual") or None,
        "notes": payload.get("notes") or "",
    }
    for opt in ("expiration_date", "manufacture_date"):
        if payload.get(opt):
            serializer_data[opt] = payload.get(opt)

    serializer = LotSerializer(data=serializer_data)
    serializer.is_valid(raise_exception=True)
    lot = serializer.save()

    pack_size_id = payload.get("pack_size_id")
    if pack_size_id:
        try:
            pack_size = ItemPackSize.objects.get(id=pack_size_id, item=lot.item, is_active=True)
            lot.pack_size = pack_size
            lot.save(update_fields=["pack_size"])
        except ItemPackSize.DoesNotExist:
            pass
    else:
        default_pack_size = ItemPackSize.objects.filter(
            item=lot.item, is_default=True, is_active=True
        ).first()
        if default_pack_size:
            lot.pack_size = default_pack_size
            lot.save(update_fields=["pack_size"])

    if lot_status == "accepted":
        lot.quantity_remaining = lot.quantity
        lot.on_hold = False
    elif lot_status == "rejected":
        lot.quantity_remaining = 0
        lot.on_hold = False
    elif lot_status == "on_hold":
        lot.quantity_remaining = lot.quantity
        lot.on_hold = True
    lot.save()

    if lot_status == "accepted":
        txn = InventoryTransaction.objects.create(
            transaction_type="receipt",
            lot=lot,
            quantity=lot.quantity,
        )
        log_lot_transaction(
            lot=lot,
            quantity_before=0.0,
            quantity_change=lot.quantity,
            transaction_type="receipt",
            reference_number=lot.po_number,
            reference_type="po_number",
            transaction_id=txn.id,
            purchase_order_id=po.id if po else None,
            notes=f"Lot received - PO: {lot.po_number}" if lot.po_number else "Lot received",
        )

        if po:
            for po_item in po.items.all():
                if po_item.item_id == lot.item_id:
                    po_item.quantity_received = float(po_item.quantity_received or 0) + float(
                        lot.quantity
                    )
                    po_item.save(update_fields=["quantity_received"])
                    item.on_order = max(0.0, float(item.on_order or 0) - float(lot.quantity))
                    item.save(update_fields=["on_order"])
                    break

            all_received = all(
                float(li.quantity_received or 0) >= float(li.quantity_ordered or 0) - 0.01
                for li in po.items.all()
            )
            if all_received and po.status == "issued":
                po.status = "received"
                po.save(update_fields=["status"])
                log_purchase_order_action(
                    po, "completed", lot=lot, notes="All items fully received"
                )
                try:
                    create_ap_entry_from_po(po)
                except Exception as e:
                    logger.warning("create_ap_entry_from_po after check-in: %s", e)
            else:
                log_purchase_order_action(
                    po,
                    "partial_check_in",
                    lot=lot,
                    notes=f"Partial check-in: {lot.quantity} received",
                )

    carrier_val = (payload.get("carrier") or "").strip()
    if not carrier_val and po and po.carrier:
        carrier_val = (po.carrier or "").strip()

    try:
        CheckInLog.objects.create(
            lot=lot,
            lot_number=lot.lot_number or "",
            item_id=lot.item.id,
            item_sku=lot.item.sku,
            item_name=lot.item.name,
            item_type=lot.item.item_type,
            item_unit_of_measure=lot.item.unit_of_measure,
            po_number=lot.po_number,
            vendor_name=lot.item.vendor if lot.item.vendor else None,
            received_date=lot.received_date,
            manufacture_date=lot.manufacture_date,
            expiration_date=lot.expiration_date,
            vendor_lot_number=lot.vendor_lot_number,
            quantity=lot.quantity,
            quantity_unit=lot.item.unit_of_measure,
            status=lot_status,
            short_reason=lot.short_reason,
            coa=coa,
            prod_free_pests=prod_free_pests,
            carrier_free_pests=carrier_free_pests,
            shipment_accepted=shipment_accepted,
            initials=initials,
            carrier=carrier_val,
            freight_actual=lot.freight_actual,
            notes=payload.get("notes") or "",
            checked_in_by=getattr(user, "username", None) or "system",
        )
    except Exception as e:
        logger.error("Failed to persist CheckInLog for lot %s: %s", lot.lot_number, e, exc_info=True)

    return lot


def reverse_check_in(lot: Lot) -> dict:
    """Thin wrapper around existing reverse_check_in_single_lot."""
    from .views import reverse_check_in_single_lot

    try:
        return reverse_check_in_single_lot(lot)
    except ValueError as e:
        raise BuyFlowError(str(e)) from e


def cancel_purchase_order(purchase_order: PurchaseOrder) -> PurchaseOrder:
    """Cancel a PO and reverse on_order if it was issued (not drop-ship)."""
    from .views import log_purchase_order_action

    if purchase_order.status == "completed":
        raise BuyFlowError("Cannot cancel a completed purchase order")

    if purchase_order.status == "issued" and not purchase_order.drop_ship:
        for po_item in purchase_order.items.select_related("item"):
            if po_item.item:
                item = po_item.item
                item.on_order = max(0, (item.on_order or 0) - po_item.quantity_ordered)
                item.save(update_fields=["on_order"])

    purchase_order.status = "cancelled"
    purchase_order.save(update_fields=["status"])
    log_purchase_order_action(purchase_order, "cancelled", notes="Purchase order cancelled")
    return purchase_order


def revise_purchase_order(original_po: PurchaseOrder) -> PurchaseOrder:
    """Create a new draft revision; supersede issued original and reverse its on_order."""
    from .views import log_purchase_order_action

    new_po = PurchaseOrder.objects.create(
        po_number=original_po.po_number,
        po_type=original_po.po_type,
        vendor_customer_name=original_po.vendor_customer_name,
        vendor_customer_id=original_po.vendor_customer_id,
        status="draft",
        revision_number=(original_po.revision_number or 0) + 1,
        original_po=original_po,
        order_number=original_po.order_number,
        expected_delivery_date=original_po.expected_delivery_date,
        required_date=original_po.required_date,
        shipping_terms=original_po.shipping_terms,
        shipping_method=original_po.shipping_method,
        ship_to_name=original_po.ship_to_name,
        ship_to_address=original_po.ship_to_address,
        ship_to_city=original_po.ship_to_city,
        ship_to_state=original_po.ship_to_state,
        ship_to_zip=original_po.ship_to_zip,
        ship_to_country=original_po.ship_to_country,
        vendor_address=original_po.vendor_address,
        vendor_city=original_po.vendor_city,
        vendor_state=original_po.vendor_state,
        vendor_zip=original_po.vendor_zip,
        vendor_country=original_po.vendor_country,
        subtotal=original_po.subtotal,
        discount=original_po.discount,
        shipping_cost=original_po.shipping_cost,
        total=original_po.total,
        coa_sds_email=original_po.coa_sds_email,
        notes=original_po.notes,
        drop_ship=getattr(original_po, "drop_ship", False),
        fulfillment_sales_order_id=getattr(original_po, "fulfillment_sales_order_id", None),
    )

    for original_item in original_po.items.all():
        PurchaseOrderItem.objects.create(
            purchase_order=new_po,
            item=original_item.item,
            quantity_ordered=original_item.quantity_ordered,
            unit_price=original_item.unit_price,
            order_uom=getattr(original_item, "order_uom", None),
            notes=original_item.notes,
        )

    if original_po.status == "issued" and not original_po.drop_ship:
        for po_item in original_po.items.select_related("item"):
            if po_item.item:
                item = po_item.item
                item.on_order = max(0, (item.on_order or 0) - po_item.quantity_ordered)
                item.save(update_fields=["on_order"])
        original_po.status = "superseded"
        original_po.save(update_fields=["status"])

    log_purchase_order_action(new_po, "created", notes=f"Revision of PO {original_po.po_number}")
    return new_po
