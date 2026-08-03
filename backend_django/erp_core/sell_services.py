"""
Shared SELL-flow services: Create sales order → Allocate → Issue → Ship (checkout).

Used by DRF ViewSets and slurp_ui Django templates so order/allocation/shipping rules
live in one place.
"""
from __future__ import annotations

import json
import logging
import re
import uuid as uuid_mod
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .lot_display_quantities import compute_lot_quantity_breakdown
from .models import (
    Customer,
    InventoryTransaction,
    Invoice,
    InvoiceItem,
    Lot,
    ProductionBatchOutput,
    SalesOrder,
    SalesOrderItem,
    SalesOrderLot,
    ShipIdempotency,
    Shipment,
    ShipmentItem,
    ShipToLocation,
)

logger = logging.getLogger(__name__)


class SellFlowError(Exception):
    """User-facing SELL flow error with optional HTTP-ish status code and extra response fields."""

    def __init__(self, message: str, status_code: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def _payload_copy(data: dict | Any) -> dict:
    """Shallow copy of request data (QueryDict → plain dict), matching ``request.data.copy()``."""
    if data is None:
        return {}
    if hasattr(data, "lists"):
        return {k: (v[0] if len(v) == 1 else v) for k, v in data.lists()}
    return dict(data)


def create_sales_order(user, data: dict) -> SalesOrder:
    """
    Create a sales order header plus lines (and optional pre-allocated lots).

    ``data`` matches the DRF create payload (customer/customer_id, ship_to_location,
    items[{item_id, quantity_ordered, unit_price, allocated_lots[]}], …).
    """
    from .serializers import SalesOrderSerializer
    from .views import _parse_staff_datetime, generate_sales_order_number

    payload = _payload_copy(data)
    is_staff = bool(getattr(user, "is_staff", False))
    if not is_staff:
        payload.pop("order_date", None)
        payload.pop("issue_date", None)

    items_data = payload.pop("items", []) or []
    if isinstance(items_data, dict):
        items_data = [items_data]
    items_data = deepcopy(list(items_data))

    # Generate sales order number if not provided (format: 3yy0000)
    if not payload.get("so_number"):
        payload["so_number"] = generate_sales_order_number()

    # Handle customer - if customer or customer_id is provided, set customer FK
    customer_id = payload.get("customer") or payload.get("customer_id")
    if customer_id:
        try:
            customer = Customer.objects.get(id=customer_id)
            payload["customer"] = customer.id
            if not payload.get("customer_name"):
                payload["customer_name"] = customer.name
            if not payload.get("customer_reference_number") and payload.get("customer_id"):
                payload["customer_reference_number"] = payload.get("customer_id")
        except Customer.DoesNotExist:
            pass

    # Ship-to location must belong to the selected customer; it also back-fills the address block
    ship_to_location_id = payload.get("ship_to_location")
    if ship_to_location_id:
        try:
            ship_to_location = ShipToLocation.objects.get(id=ship_to_location_id)
        except ShipToLocation.DoesNotExist as e:
            raise SellFlowError("Ship-to location not found", status_code=404) from e

        cust_pk = None
        if customer_id is not None:
            try:
                cust_pk = int(customer_id)
            except (TypeError, ValueError):
                cust_pk = None
        if cust_pk is not None and ship_to_location.customer_id != cust_pk:
            raise SellFlowError("Ship-to location does not belong to the selected customer")

        if not payload.get("customer_address"):
            payload["customer_address"] = ship_to_location.address
        if not payload.get("customer_city"):
            payload["customer_city"] = ship_to_location.city
        if not payload.get("customer_state"):
            payload["customer_state"] = ship_to_location.state or ""
        if not payload.get("customer_zip"):
            payload["customer_zip"] = ship_to_location.zip_code
        if not payload.get("customer_country"):
            payload["customer_country"] = ship_to_location.country
        if not payload.get("customer_phone"):
            payload["customer_phone"] = ship_to_location.phone or ""

    serializer = SalesOrderSerializer(data=payload)
    if not serializer.is_valid():
        raise SellFlowError("", extra={"_serializer_errors": serializer.errors})
    validated_data = serializer.validated_data

    # customer is a SerializerMethodField (read-only); resolve FK from request payload
    customer_obj = validated_data.get("customer")
    if customer_obj is None:
        raw_c = payload.get("customer") or payload.get("customer_id")
        if raw_c is not None:
            try:
                customer_obj = Customer.objects.get(pk=int(raw_c))
            except (ValueError, TypeError, Customer.DoesNotExist):
                customer_obj = None

    ship_to_obj = validated_data.get("ship_to_location")

    order_date_val = timezone.now()
    if is_staff and payload.get("order_date"):
        parsed_od = _parse_staff_datetime(payload.get("order_date"))
        if parsed_od:
            order_date_val = parsed_od

    for row in items_data:
        iid = row.get("item_id") or row.get("item")
        if not iid:
            raise SellFlowError("item_id is required for each sales order item")

    try:
        with transaction.atomic():
            sales_order = SalesOrder.objects.create(
                so_number=validated_data["so_number"],
                customer=customer_obj,
                ship_to_location=ship_to_obj,
                customer_name=validated_data.get("customer_name") or "",
                customer_legacy_id=validated_data.get("customer_legacy_id"),
                customer_reference_number=validated_data.get("customer_reference_number"),
                customer_address=validated_data.get("customer_address"),
                customer_city=validated_data.get("customer_city"),
                customer_state=validated_data.get("customer_state"),
                customer_zip=validated_data.get("customer_zip"),
                customer_country=validated_data.get("customer_country"),
                customer_phone=validated_data.get("customer_phone"),
                contact=validated_data.get("contact"),
                order_date=order_date_val,
                expected_ship_date=validated_data.get("expected_ship_date"),
                actual_ship_date=validated_data.get("actual_ship_date"),
                status=validated_data.get("status", "draft"),
                notes=validated_data.get("notes"),
                carrier=validated_data.get("carrier"),
                tracking_number=validated_data.get("tracking_number"),
                drop_ship=bool(validated_data.get("drop_ship", False)),
            )

            for item_data in items_data:
                allocated_lots_data = item_data.pop("allocated_lots", [])

                item_id = item_data.get("item_id") or item_data.get("item")
                so_item = SalesOrderItem.objects.create(
                    sales_order=sales_order,
                    item_id=item_id,
                    quantity_ordered=item_data.get("quantity_ordered", 0),
                    unit_price=item_data.get("unit_price"),
                    notes=item_data.get("notes"),
                )

                if allocated_lots_data:
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT name FROM sqlite_master "
                                "WHERE type='table' AND name='erp_core_salesorderlot'"
                            )
                            if cursor.fetchone():
                                for lot_data in allocated_lots_data:
                                    SalesOrderLot.objects.create(
                                        sales_order_item=so_item,
                                        lot_id=lot_data.get("lot_id"),
                                        quantity_allocated=lot_data.get("quantity_allocated", 0),
                                    )
                                    so_item.quantity_allocated += lot_data.get(
                                        "quantity_allocated", 0
                                    )
                                so_item.save()
                    except Exception as e:
                        logger.warning(
                            "SalesOrderLot table does not exist, skipping lot allocations: %s", e
                        )
    except SellFlowError:
        raise
    except Exception as e:
        import traceback

        logger.error("Failed to create sales order: %s", e)
        logger.error("Traceback: %s", traceback.format_exc())
        raise SellFlowError(
            "Failed to create sales order",
            status_code=500,
            extra={
                "detail": str(e),
                "debug_info": {
                    "so_number": validated_data.get("so_number"),
                    "customer_id": getattr(customer_obj, "id", None) if customer_obj else None,
                    "ship_to_id": ship_to_obj.id if ship_to_obj else None,
                },
            },
        ) from e

    return sales_order


def allocate_sales_order(sales_order: SalesOrder, data: dict) -> SalesOrder:
    """
    Allocate lots to sales order items.

    Creates distributed item lots when raw materials are supplied. Drop-ship orders get a
    virtual (lot-free) allocation and go straight to ``ready_for_shipment``.
    """
    from .inventory_fg_visibility import (
        GATED_PRODUCT_CATEGORIES,
        lot_allowed_for_gated_fg_allocation,
    )
    from .views import generate_lot_number, log_lot_depletion, log_lot_transaction

    payload = _payload_copy(data)
    items_data = payload.get("items", []) or []
    allow_prerepack_allocation = bool(payload.get("allow_prerepack_allocation"))

    closed_batch_output_lot_ids = set(
        ProductionBatchOutput.objects.filter(batch__status="closed").values_list(
            "lot_id", flat=True
        )
    )

    if sales_order.drop_ship:
        with transaction.atomic():
            for so_item in sales_order.items.all():
                SalesOrderLot.objects.filter(sales_order_item=so_item).delete()
                so_item.quantity_allocated = float(so_item.quantity_ordered or 0)
                so_item.save(update_fields=["quantity_allocated"])
            sales_order.status = "ready_for_shipment"
            sales_order.save(update_fields=["status"])
        return sales_order

    with transaction.atomic():
        for item_data in items_data:
            item_id = item_data.get("item_id")
            is_distributed = item_data.get("is_distributed", False)
            allocations = item_data.get("allocations", [])
            raw_materials = item_data.get("raw_materials", [])

            try:
                so_item = SalesOrderItem.objects.get(sales_order=sales_order, item_id=item_id)
            except SalesOrderItem.DoesNotExist as e:
                raise SellFlowError(
                    f"Sales order item for item {item_id} not found", status_code=404
                ) from e

            SalesOrderLot.objects.filter(sales_order_item=so_item).delete()
            so_item.quantity_allocated = 0.0

            if is_distributed and raw_materials:
                # Distributed items: build a new lot from checked-in raw material lots
                distributed_item = so_item.item
                total_quantity = 0.0
                raw_material_lots = []

                for rm_data in raw_materials:
                    lot_id = rm_data.get("lot_id")
                    quantity = float(rm_data.get("quantity", 0))

                    try:
                        lot = Lot.objects.get(id=lot_id, status="accepted")
                    except Lot.DoesNotExist as e:
                        raise SellFlowError(
                            f"Lot {lot_id} not found or not accepted", status_code=404
                        ) from e
                    max_use = float(
                        compute_lot_quantity_breakdown(lot)["quantity_available_for_use"]
                    )
                    if quantity > max_use + 1e-6:
                        raise SellFlowError(
                            f"Insufficient quantity in lot {lot.lot_number}. "
                            f"Available: {max_use}, Requested: {quantity}"
                        )
                    raw_material_lots.append((lot, quantity))
                    total_quantity += quantity

                new_lot_number = generate_lot_number()
                new_lot = Lot.objects.create(
                    lot_number=new_lot_number,
                    item=distributed_item,
                    quantity=total_quantity,
                    quantity_remaining=total_quantity,
                    received_date=timezone.now(),
                    status="accepted",
                )

                for raw_lot, qty in raw_material_lots:
                    quantity_before = raw_lot.quantity_remaining
                    raw_lot.quantity_remaining -= qty
                    raw_lot.save()

                    txn = InventoryTransaction.objects.create(
                        transaction_type="production",
                        lot=raw_lot,
                        quantity=-qty,
                        reference_number=sales_order.so_number,
                        notes=f"Allocated to distributed item lot {new_lot_number}",
                    )

                    log_lot_transaction(
                        lot=raw_lot,
                        quantity_before=quantity_before,
                        quantity_change=-qty,
                        transaction_type="production_input",
                        reference_number=sales_order.so_number,
                        reference_type="so_number",
                        transaction_id=txn.id,
                        sales_order_id=sales_order.id,
                        notes=(
                            f"Used for distributed item lot {new_lot_number} "
                            f"in sales order {sales_order.so_number}"
                        ),
                    )

                    log_lot_depletion(
                        lot=raw_lot,
                        quantity_before=quantity_before,
                        quantity_used=qty,
                        depletion_method="production",
                        reference_number=sales_order.so_number,
                        reference_type="so_number",
                        sales_order_id=sales_order.id,
                        transaction_id=txn.id,
                        notes=(
                            f"Used for distributed item lot {new_lot_number} "
                            f"in sales order {sales_order.so_number}"
                        ),
                    )

                txn = InventoryTransaction.objects.create(
                    transaction_type="production",
                    lot=new_lot,
                    quantity=total_quantity,
                    reference_number=sales_order.so_number,
                    notes=f"Created from raw materials for sales order {sales_order.so_number}",
                )

                log_lot_transaction(
                    lot=new_lot,
                    quantity_before=0.0,
                    quantity_change=total_quantity,
                    transaction_type="production_output",
                    reference_number=sales_order.so_number,
                    reference_type="so_number",
                    transaction_id=txn.id,
                    sales_order_id=sales_order.id,
                    notes=f"Created from raw materials for sales order {sales_order.so_number}",
                )

                SalesOrderLot.objects.create(
                    sales_order_item=so_item,
                    lot=new_lot,
                    quantity_allocated=total_quantity,
                )
                so_item.quantity_allocated = total_quantity

            else:
                # Regular items - allocate from existing lots
                for allocation in allocations:
                    lot_id = allocation.get("lot_id")
                    quantity = float(allocation.get("quantity", 0))

                    lot = (
                        Lot.objects.select_related("item")
                        .filter(id=lot_id, status__in=["accepted", "on_hold"])
                        .first()
                    )
                    if not lot:
                        raise SellFlowError(
                            f"Lot {lot_id} not found or not in accepted/on-hold status",
                            status_code=404,
                        )
                    if lot.item_id != int(item_id):
                        line_sku = (getattr(so_item.item, "sku", None) or "").strip().upper()
                        lot_sku = (getattr(lot.item, "sku", None) or "").strip().upper()
                        if not line_sku or line_sku != lot_sku:
                            raise SellFlowError(
                                f"Lot {lot.lot_number} is for a different item than this order line."
                            )
                    max_use = float(
                        compute_lot_quantity_breakdown(lot)["quantity_available_for_use"]
                    )
                    if quantity > max_use + 1e-6:
                        raise SellFlowError(
                            f"Insufficient quantity in lot {lot.lot_number}. "
                            f"Available: {max_use}, Requested: {quantity}"
                        )
                    # Distributed items: only repack output lots (same as Finished Good inventory tab),
                    # unless the client explicitly allows pre-repack / raw-inventory allocation
                    # (vendor-labeled stock).
                    if (getattr(so_item.item, "item_type", None) or "").strip() == "distributed_item":
                        if not allow_prerepack_allocation and not ProductionBatchOutput.objects.filter(
                            lot_id=lot.id,
                            batch__batch_type="repack",
                            batch__status="closed",
                        ).exists():
                            raise SellFlowError(
                                f"Lot {lot.lot_number} is pre-repack or vendor stock. "
                                "For distributed items, allocate only from lots created by a "
                                "completed repack batch, or enable "
                                '"include raw / pre-repack lots" when saving allocations.'
                            )

                    itype = (getattr(so_item.item, "item_type", None) or "").strip()
                    pcat = (getattr(so_item.item, "product_category", None) or "").strip()
                    if itype == "finished_good" and pcat in GATED_PRODUCT_CATEGORIES:
                        if not lot_allowed_for_gated_fg_allocation(
                            lot,
                            so_item.item,
                            closed_batch_output_lot_ids,
                            allow_prerepack_allocation,
                        ):
                            raise SellFlowError(
                                f"Lot {lot.lot_number} is not from a closed repack or production "
                                f"batch. For gated finished goods "
                                f'({pcat.replace("_", " ")}), pick batch output lots only, '
                                f'or enable "include raw / pre-repack lots" when saving allocations.'
                            )

                    SalesOrderLot.objects.create(
                        sales_order_item=so_item,
                        lot=lot,
                        quantity_allocated=quantity,
                    )
                    so_item.quantity_allocated += quantity

            so_item.save()

        sales_order.refresh_from_db()

        all_fully_allocated = all(
            item.quantity_allocated >= item.quantity_ordered for item in sales_order.items.all()
        )

        if all_fully_allocated:
            sales_order.status = "ready_for_shipment"
        else:
            # Partial allocation: 'issued' orders stay issued so the user can keep allocating.
            total_allocated = sum(item.quantity_allocated for item in sales_order.items.all())
            if total_allocated > 0:
                if sales_order.status == "issued":
                    pass
                else:
                    sales_order.status = "allocated"
            else:
                if sales_order.status != "issued":
                    sales_order.status = "draft"
        sales_order.save()

    return sales_order


def issue_sales_order(sales_order: SalesOrder, user, *, issue_date=None) -> SalesOrder:
    """Issue a draft sales order (status → ``issued``) and email the confirmation PDF."""
    from .views import _parse_staff_datetime

    if sales_order.status != "draft":
        raise SellFlowError(
            f"Sales order must be in draft status to issue. "
            f"Current status: {sales_order.status}"
        )

    if issue_date is not None and str(issue_date).strip() != "":
        if not getattr(user, "is_staff", False):
            raise SellFlowError(
                "Only staff can set a custom issue date (God mode).", status_code=403
            )
        parsed = _parse_staff_datetime(issue_date)
        if parsed is None:
            raise SellFlowError("Invalid issue_date or order_date. Use YYYY-MM-DD or ISO datetime.")
        sales_order.order_date = parsed

    sales_order.status = "issued"
    sales_order.save()

    try:
        from .email_service import send_sales_order_confirmation_email
        from .sales_order_pdf_html import generate_sales_order_pdf_from_html

        pdf_content = generate_sales_order_pdf_from_html(sales_order)
        send_sales_order_confirmation_email(sales_order, pdf_content)
    except Exception as e:
        logger.error("Failed to send sales order confirmation email: %s", e)

    return sales_order


def ship_sales_order(
    sales_order: SalesOrder,
    user,
    data: dict,
    *,
    idempotency_key: str | None = None,
    serializer_context: dict | None = None,
) -> dict:
    """
    Check out (ship) a sales order, fully or partially, and create the shipment invoice.

    Returns the API response payload: ``{'sales_order': …, 'invoice': …, 'shipment': …}``.
    Drop-ship lines with no lot allocations skip inventory movement.
    """
    from .serializers import InvoiceSerializer, SalesOrderSerializer
    from .views import (
        _normalize_checkout_ship_quantity,
        log_lot_depletion,
        log_lot_transaction,
    )

    payload = _payload_copy(data)
    context = serializer_context or {}

    idem_key = (idempotency_key or "").strip()[:128]
    if idem_key:
        prev = ShipIdempotency.objects.filter(key=idem_key).first()
        if prev:
            if prev.sales_order_id != sales_order.id:
                raise SellFlowError(
                    "This idempotency key was already used for another sales order.",
                    status_code=409,
                )
            return json.loads(prev.response_json)

    ship_date_str = payload.get("ship_date")
    invoice_date_str = payload.get("invoice_date", ship_date_str)
    tracking_number = payload.get("tracking_number", "").strip()
    carrier = (payload.get("carrier") or "").strip()
    items_to_ship = payload.get("items", [])  # [{item_id, quantity}] for partial shipments
    combined_shipment_key = None
    raw_ck = payload.get("combined_shipment_key")
    if raw_ck:
        try:
            combined_shipment_key = uuid_mod.UUID(str(raw_ck))
        except (ValueError, TypeError, AttributeError):
            combined_shipment_key = None
    combined_freight_skip = bool(payload.get("combined_freight_skip"))

    if sales_order.status not in ("issued", "ready_for_shipment"):
        raise SellFlowError(
            f"Sales order must be issued or ready for shipment to checkout. "
            f"Current status: {sales_order.status}"
        )

    # Drop ship uses virtual allocation only
    total_allocated = sum(item.quantity_allocated for item in sales_order.items.all())
    if total_allocated == 0 and not sales_order.drop_ship:
        raise SellFlowError("Sales order must have material allocated before checkout")

    if not ship_date_str:
        raise SellFlowError("ship_date is required")

    try:
        ship_date = datetime.strptime(ship_date_str, "%Y-%m-%d").date()
        invoice_date = (
            datetime.strptime(invoice_date_str, "%Y-%m-%d").date()
            if invoice_date_str
            else ship_date
        )
    except ValueError as e:
        raise SellFlowError("Invalid date format. Use YYYY-MM-DD") from e

    use_partial = bool(items_to_ship)

    with transaction.atomic():
        # Serialize concurrent ship() calls (prevents duplicate shipments from double-submit / races).
        sales_order = (
            SalesOrder.objects.prefetch_related("items__item")
            .select_for_update()
            .get(pk=sales_order.pk)
        )
        if sales_order.status not in ("issued", "ready_for_shipment"):
            raise SellFlowError(
                f"Sales order must be issued or ready for shipment to checkout. "
                f"Current status: {sales_order.status}"
            )
        total_allocated_locked = sum(item.quantity_allocated for item in sales_order.items.all())
        if total_allocated_locked == 0 and not sales_order.drop_ship:
            raise SellFlowError("Sales order must have material allocated before checkout")

        # Checkout requires carrier, piece count, per-piece dimensions & weights (packing list).
        # Tracking optional.
        if not carrier:
            raise SellFlowError(
                "Carrier is required at checkout (shown on packing list and invoice)."
            )
        pieces_raw = payload.get("pieces")
        try:
            pieces_int = int(pieces_raw)
        except (TypeError, ValueError) as e:
            raise SellFlowError("pieces must be a positive integer.") from e
        if pieces_int < 1:
            raise SellFlowError("pieces must be at least 1.")

        piece_dims_in = payload.get("piece_dimensions")
        if not isinstance(piece_dims_in, list):
            raise SellFlowError(
                "piece_dimensions must be a JSON array with one dimension string per piece."
            )
        if len(piece_dims_in) != pieces_int:
            raise SellFlowError(
                f"piece_dimensions must have {pieces_int} entries (one per piece); "
                f"got {len(piece_dims_in)}."
            )
        piece_dims_clean = []
        for idx, d in enumerate(piece_dims_in):
            s = (str(d) if d is not None else "").strip()
            if not s:
                raise SellFlowError(f"Dimensions are required for piece {idx + 1}.")
            piece_dims_clean.append(s)

        piece_weights_in = payload.get("piece_weights")
        if not isinstance(piece_weights_in, list):
            raise SellFlowError("piece_weights must be a JSON array with one weight per piece.")
        if len(piece_weights_in) != pieces_int:
            raise SellFlowError(
                f"piece_weights must have {pieces_int} entries (one per piece); "
                f"got {len(piece_weights_in)}."
            )
        piece_weights_clean = []
        for idx, w in enumerate(piece_weights_in):
            s = (str(w) if w is not None else "").strip()
            if not s:
                raise SellFlowError(f"Weight is required for piece {idx + 1}.")
            piece_weights_clean.append(s)

        dimensions_summary = "; ".join(
            f"Piece {i + 1}: {d} | {wt}"
            for i, (d, wt) in enumerate(zip(piece_dims_clean, piece_weights_clean))
        )

        # Create shipment record (tracking number, dimensions, pieces can be set at checkout)
        ship_dt = timezone.make_aware(datetime.combine(ship_date, datetime.min.time()))
        expected_dt = None
        if payload.get("expected_ship_date"):
            try:
                from django.utils.dateparse import parse_datetime

                expected_dt = parse_datetime(payload.get("expected_ship_date"))
                if expected_dt and timezone.is_naive(expected_dt):
                    expected_dt = timezone.make_aware(expected_dt)
            except Exception:
                pass
        if expected_dt is None and sales_order.expected_ship_date:
            expected_dt = sales_order.expected_ship_date
        shipment = Shipment.objects.create(
            sales_order=sales_order,
            expected_ship_date=expected_dt,
            ship_date=ship_dt,
            tracking_number=tracking_number or "",
            notes=payload.get("notes", ""),
            dimensions=dimensions_summary,
            pieces=pieces_int,
            piece_dimensions=piece_dims_clean,
            piece_weights=piece_weights_clean,
            combined_shipment_key=combined_shipment_key,
        )

        # Normalize item_id to int for dict lookup (JSON may send string)
        items_shipped_map = {}
        if use_partial:
            for item_data in items_to_ship:
                raw_id = item_data.get("item_id") or item_data.get("sales_order_item_id")
                item_id = int(raw_id) if raw_id is not None else None
                quantity_to_ship = float(item_data.get("quantity", 0))
                if item_id is not None and quantity_to_ship > 0:
                    items_shipped_map[item_id] = quantity_to_ship
        else:
            for so_item in sales_order.items.all():
                if so_item.quantity_allocated > 0:
                    items_shipped_map[so_item.id] = so_item.quantity_allocated

        # Reduce lot quantities and create inventory transactions
        for so_item in sales_order.items.all():
            raw_qty = items_shipped_map.get(so_item.id, 0)
            if raw_qty <= 0:
                continue
            uom = getattr(so_item.item, "unit_of_measure", None) or ""
            ok, quantity_to_ship = _normalize_checkout_ship_quantity(
                raw_qty, so_item.quantity_allocated, uom
            )
            if not ok:
                raise SellFlowError(
                    f"Cannot ship {raw_qty} of {so_item.item.name}. "
                    f"Only {so_item.quantity_allocated} is allocated."
                )

            # Ship from allocated lots proportionally or FIFO
            remaining_to_ship = quantity_to_ship
            allocations = SalesOrderLot.objects.filter(sales_order_item=so_item).order_by(
                "created_at"
            )

            if sales_order.drop_ship and not allocations.exists():
                so_item.quantity_shipped += quantity_to_ship
                so_item.quantity_allocated -= quantity_to_ship
                so_item.save(update_fields=["quantity_shipped", "quantity_allocated"])
                ShipmentItem.objects.create(
                    shipment=shipment,
                    sales_order_item=so_item,
                    quantity_shipped=quantity_to_ship,
                )
                continue

            for allocation in allocations:
                if remaining_to_ship <= 0:
                    break

                lot = allocation.lot
                quantity_from_allocation = min(remaining_to_ship, allocation.quantity_allocated)

                if lot.quantity_remaining < quantity_from_allocation:
                    raise SellFlowError(
                        f"Insufficient quantity in lot {lot.lot_number}. "
                        f"Available: {lot.quantity_remaining}, "
                        f"Required: {quantity_from_allocation}"
                    )

                quantity_before = lot.quantity_remaining

                inv_txn = InventoryTransaction.objects.create(
                    transaction_type="adjustment",
                    lot=lot,
                    quantity=-quantity_from_allocation,
                    reference_number=sales_order.so_number,
                    notes=(
                        f"Shipped for sales order {sales_order.so_number} - "
                        f"Shipment {shipment.id}"
                    ),
                )

                log_lot_transaction(
                    lot=lot,
                    quantity_before=quantity_before,
                    quantity_change=-quantity_from_allocation,
                    transaction_type="sale",
                    reference_number=sales_order.so_number,
                    reference_type="so_number",
                    transaction_id=inv_txn.id,
                    sales_order_id=sales_order.id,
                    notes=(
                        f"Shipped for sales order {sales_order.so_number} - "
                        f"Shipment {shipment.id}"
                    ),
                )

                lot.quantity_remaining -= quantity_from_allocation
                lot.save()

                # Keep the SalesOrderLot row at quantity 0 after a full ship so customer COA
                # (LotCoaCustomerCopy) and list/detail APIs still expose allocation history.
                allocation.quantity_allocated -= quantity_from_allocation
                if allocation.quantity_allocated <= 0:
                    allocation.quantity_allocated = 0.0
                allocation.save()

                log_lot_depletion(
                    lot=lot,
                    quantity_before=quantity_before,
                    quantity_used=quantity_from_allocation,
                    depletion_method="sales",
                    reference_number=sales_order.so_number,
                    reference_type="so_number",
                    sales_order_id=sales_order.id,
                    transaction_id=inv_txn.id,
                    notes=(
                        f"Shipped for sales order {sales_order.so_number} - "
                        f"Shipment {shipment.id}"
                    ),
                )

                remaining_to_ship -= quantity_from_allocation

            so_item.quantity_shipped += quantity_to_ship
            so_item.quantity_allocated -= quantity_to_ship
            so_item.save()

            ShipmentItem.objects.create(
                shipment=shipment,
                sales_order_item=so_item,
                quantity_shipped=quantity_to_ship,
            )

        # Update sales order status, tracking, and carrier
        sales_order.actual_ship_date = timezone.make_aware(
            datetime.combine(ship_date, datetime.min.time())
        )
        if not sales_order.tracking_number:
            sales_order.tracking_number = tracking_number
        if carrier:
            sales_order.carrier = carrier

        all_fully_shipped = all(
            item.quantity_shipped >= item.quantity_ordered for item in sales_order.items.all()
        )

        if all_fully_shipped:
            sales_order.status = "completed"
        else:
            # Still has outstanding balance - keep as ready_for_shipment (allocations remain)
            # or issued (can allocate more).
            total_remaining_allocated = sum(
                item.quantity_allocated for item in sales_order.items.all()
            )
            if total_remaining_allocated > 0:
                sales_order.status = "ready_for_shipment"
            else:
                sales_order.status = "issued"

        sales_order.save()

        invoice = _create_shipment_invoice(
            sales_order=sales_order,
            shipment=shipment,
            invoice_date=invoice_date,
            combined_freight_skip=combined_freight_skip,
        )

        # Create invoice items from shipped quantities in this shipment
        for shipment_item in shipment.items.all():
            if shipment_item.quantity_shipped > 0:
                so_item = shipment_item.sales_order_item
                line_total = (so_item.unit_price or 0.0) * shipment_item.quantity_shipped
                InvoiceItem.objects.create(
                    invoice=invoice,
                    item=so_item.item,
                    sales_order_item=so_item,
                    description=so_item.item.name,
                    quantity=shipment_item.quantity_shipped,
                    unit_price=so_item.unit_price or 0.0,
                    total=line_total,
                    notes="",
                )

    response_payload = {
        "sales_order": SalesOrderSerializer(sales_order, context=context).data,
        "invoice": InvoiceSerializer(invoice).data,
        "shipment": {
            "id": shipment.id,
            "ship_date": shipment.ship_date.isoformat(),
            "tracking_number": shipment.tracking_number,
            "combined_shipment_key": (
                str(combined_shipment_key) if combined_shipment_key else None
            ),
        },
    }
    if idem_key:
        try:
            ShipIdempotency.objects.create(
                key=idem_key,
                sales_order=sales_order,
                shipment=shipment,
                response_json=json.dumps(response_payload, cls=DjangoJSONEncoder),
            )
        except IntegrityError:
            prev = ShipIdempotency.objects.filter(key=idem_key).first()
            if prev:
                return json.loads(prev.response_json)
            raise
    return response_payload


def combined_ship_sales_orders(user, data: dict) -> dict:
    """
    Check out multiple sales orders in one atomic operation: same carrier / tracking /
    pieces / dimensions, one combined packing list key. Freight on the first order only.
    Requires the same customer and ship-to on every order.
    """
    orders_spec = data.get("orders")
    if not isinstance(orders_spec, list) or len(orders_spec) < 2:
        raise SellFlowError(
            'Provide "orders": a list of at least 2 objects, each with "sales_order_id" '
            '(or "id") and optional "items" for partial ship.'
        )

    parsed = []
    for spec in orders_spec:
        if not isinstance(spec, dict):
            raise SellFlowError("Each order entry must be an object.")
        raw_id = spec.get("sales_order_id") or spec.get("id")
        if raw_id is None:
            raise SellFlowError("Each order needs sales_order_id or id.")
        try:
            oid = int(raw_id)
        except (TypeError, ValueError) as e:
            raise SellFlowError(f"Invalid sales order id: {raw_id!r}") from e
        parsed.append((oid, spec))

    ids = [p[0] for p in parsed]
    if len(set(ids)) != len(ids):
        raise SellFlowError("Duplicate sales order in orders list.")

    base = {k: deepcopy(v) for k, v in (data or {}).items() if k != "orders"}
    key = uuid_mod.uuid4()
    results = []

    with transaction.atomic():
        sos = list(
            SalesOrder.objects.select_for_update()
            .filter(pk__in=ids)
            .prefetch_related("items")
            .order_by("id")
        )
        if len(sos) != len(ids):
            raise SellFlowError("One or more sales orders were not found.")
        by_id = {so.id: so for so in sos}

        first = by_id[ids[0]]
        cust_id = first.customer_id
        st_id = first.ship_to_location_id
        for oid in ids:
            so = by_id[oid]
            if so.customer_id != cust_id or so.ship_to_location_id != st_id:
                raise SellFlowError(
                    "Combined checkout requires the same customer and ship-to location "
                    "on every order."
                )
            if so.status not in ("issued", "ready_for_shipment"):
                raise SellFlowError(
                    f"Order {so.so_number} must be issued or ready for shipment "
                    f"(status is {so.status})."
                )
            total_alloc = sum(float(getattr(i, "quantity_allocated", 0) or 0) for i in so.items.all())
            if total_alloc <= 0 and not getattr(so, "drop_ship", False):
                raise SellFlowError(
                    f"Order {so.so_number} has no allocated quantity to ship."
                )

        for idx, (oid, spec) in enumerate(parsed):
            payload = dict(base)
            if spec.get("items") is not None:
                payload["items"] = spec["items"]
            payload["combined_shipment_key"] = str(key)
            payload["combined_freight_skip"] = idx > 0
            results.append(ship_sales_order(by_id[oid], user, payload))

    return {"combined_shipment_key": str(key), "shipments": results}


def _create_shipment_invoice(
    *,
    sales_order: SalesOrder,
    shipment: Shipment,
    invoice_date,
    combined_freight_skip: bool,
) -> Invoice:
    """
    Create the customer invoice for one shipment.

    Falls back to raw SQL on legacy databases whose ``erp_core_invoice`` table predates the
    ``sales_order_id`` column.
    """
    from .views import create_ar_entry_from_invoice, generate_invoice_number

    invoice_number = generate_invoice_number()

    # Calculate due date from payment terms (e.g. "Net 30" → +30 days)
    due_date = invoice_date
    if sales_order.customer and sales_order.customer.payment_terms:
        match = re.search(r"(\d+)", sales_order.customer.payment_terms)
        if match:
            due_date = invoice_date + timedelta(days=int(match.group(1)))

    subtotal = sum(
        item.sales_order_item.unit_price * item.quantity_shipped
        for item in shipment.items.all()
        if item.sales_order_item.unit_price
    )
    freight = getattr(sales_order, "freight", 0.0) or 0.0
    if combined_freight_skip:
        freight = 0.0
    discount = getattr(sales_order, "discount", 0.0) or 0.0
    tax = 0.0
    grand_total = subtotal + freight + tax - discount

    # Check what columns actually exist in Invoice table and which are NOT NULL
    available_columns = set()
    not_null_columns = set()
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(erp_core_invoice)")
            for row in cursor.fetchall():
                col_name = row[1]
                is_not_null = row[3]
                available_columns.add(col_name)
                if is_not_null and col_name != "id":
                    not_null_columns.add(col_name)
    except Exception:
        available_columns = {"id", "invoice_number", "invoice_date", "created_at", "updated_at"}
        not_null_columns = {"invoice_number", "invoice_date"}

    if "sales_order_id" not in available_columns:
        # Raw SQL insert so the ORM never tries to set the missing column
        now = timezone.now()
        columns = ["invoice_number"]
        values = [invoice_number]
        placeholders = ["?"]

        if "invoice_type" in available_columns:
            columns.append("invoice_type")
            values.append("customer")
            placeholders.append("?")
        if "customer_vendor_name" in available_columns:
            columns.append("customer_vendor_name")
            customer_name = sales_order.customer_name
            if not customer_name and sales_order.customer:
                customer_name = sales_order.customer.name
            if not customer_name:
                customer_name = "Unknown Customer"
            values.append(customer_name)
            placeholders.append("?")
        if "customer_vendor_id" in available_columns:
            columns.append("customer_vendor_id")
            customer_id = sales_order.customer_legacy_id
            if not customer_id and sales_order.customer:
                customer_id = str(sales_order.customer.id)
            values.append(customer_id)
            placeholders.append("?")

        if "invoice_date" in available_columns:
            columns.append("invoice_date")
            values.append(invoice_date)
            placeholders.append("?")
        if "due_date" in available_columns:
            columns.append("due_date")
            values.append(due_date)
            placeholders.append("?")
        if "status" in available_columns:
            columns.append("status")
            values.append("draft")
            placeholders.append("?")
        if "subtotal" in available_columns:
            columns.append("subtotal")
            values.append(subtotal)
            placeholders.append("?")
        if "freight" in available_columns:
            columns.append("freight")
            values.append(freight)
            placeholders.append("?")
        if "tax" in available_columns:
            columns.append("tax")
            values.append(tax)
            placeholders.append("?")
        if "tax_amount" in available_columns:
            columns.append("tax_amount")
            values.append(tax)
            placeholders.append("?")
        if "discount" in available_columns:
            columns.append("discount")
            values.append(discount)
            placeholders.append("?")
        if "grand_total" in available_columns:
            columns.append("grand_total")
            values.append(grand_total)
            placeholders.append("?")
        if "total_amount" in available_columns:
            columns.append("total_amount")
            values.append(grand_total)
            placeholders.append("?")
        if "paid_amount" in available_columns:
            columns.append("paid_amount")
            values.append(0.0)
            placeholders.append("?")
        if "notes" in available_columns:
            columns.append("notes")
            notes_text = (
                f"Auto-generated from sales order {sales_order.so_number} - "
                f"Shipment {shipment.id}"
            )
            # Escape % so Django's query logging (sql % params) doesn't choke
            notes_text = notes_text.replace("%", "%%")
            values.append(notes_text)
            placeholders.append("?")
        if "created_at" in available_columns:
            columns.append("created_at")
            values.append(now)
            placeholders.append("?")
        if "updated_at" in available_columns:
            columns.append("updated_at")
            values.append(now)
            placeholders.append("?")

        # Ensure all NOT NULL columns are included
        for col in not_null_columns:
            if col not in columns and col != "id":
                if col == "invoice_type" and "invoice_type" in available_columns:
                    columns.append("invoice_type")
                    values.append("customer")
                    placeholders.append("?")
                elif col == "customer_vendor_name" and "customer_vendor_name" in available_columns:
                    columns.append("customer_vendor_name")
                    customer_name = sales_order.customer_name or (
                        sales_order.customer.name if sales_order.customer else "Unknown Customer"
                    )
                    values.append(customer_name)
                    placeholders.append("?")
                elif col == "invoice_date" and "invoice_date" in available_columns:
                    columns.append("invoice_date")
                    values.append(invoice_date)
                    placeholders.append("?")
                elif col == "status" and "status" in available_columns:
                    columns.append("status")
                    values.append("draft")
                    placeholders.append("?")
                elif col == "subtotal" and "subtotal" in available_columns:
                    columns.append("subtotal")
                    values.append(subtotal)
                    placeholders.append("?")
                elif col == "tax_amount" and "tax_amount" in available_columns:
                    columns.append("tax_amount")
                    values.append(tax)
                    placeholders.append("?")
                elif col == "total_amount" and "total_amount" in available_columns:
                    columns.append("total_amount")
                    values.append(grand_total)
                    placeholders.append("?")
                elif col == "paid_amount" and "paid_amount" in available_columns:
                    columns.append("paid_amount")
                    values.append(0.0)
                    placeholders.append("?")

        if len(placeholders) != len(values):
            raise ValueError(
                f"Placeholder count ({len(placeholders)}) doesn't match value count "
                f"({len(values)}). Columns: {columns}"
            )

        columns_str = ", ".join(columns)
        placeholders_str = ", ".join(placeholders)
        sql = "INSERT INTO erp_core_invoice (" + columns_str + ") VALUES (" + placeholders_str + ")"

        # Use Django's connection so we stay in the same transaction (avoids "database is locked")
        with connection.cursor() as raw_cursor:
            raw_cursor.execute(sql, tuple(values))
            invoice_id = raw_cursor.lastrowid

        if not invoice_id:
            raise ValueError("Failed to create invoice - no ID returned")

        with connection.cursor() as check_cursor:
            check_cursor.execute("PRAGMA table_info(erp_core_invoice)")
            columns = [row[1] for row in check_cursor.fetchall()]
            if "sales_order_id" in columns:
                check_cursor.execute(
                    "UPDATE erp_core_invoice SET sales_order_id = ? WHERE id = ?",
                    [sales_order.id, invoice_id],
                )

        invoice = Invoice.objects.get(id=invoice_id)
        create_ar_entry_from_invoice(invoice)
        return invoice

    # ORM path - include fields required by DB columns added in migrations (e.g. invoice_type)
    invoice_data = {
        "invoice_number": invoice_number,
        "sales_order": sales_order,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "status": "draft",
        "subtotal": subtotal,
        "freight": freight,
        "tax": tax,
        "discount": discount,
        "grand_total": grand_total,
        "notes": (
            f"Auto-generated from sales order {sales_order.so_number} - Shipment {shipment.id}"
        ),
    }
    invoice_data["invoice_type"] = "customer"
    customer_name = (
        getattr(sales_order, "customer_name", None)
        or (sales_order.customer.name if sales_order.customer else None)
        or "Unknown Customer"
    )
    invoice_data["customer_vendor_name"] = customer_name or "Unknown Customer"
    invoice_data["tax_amount"] = tax
    invoice_data["total_amount"] = grand_total
    invoice_data["paid_amount"] = 0.0
    try:
        invoice = Invoice.objects.create(**invoice_data)
    except Exception as e:
        logger.error("Error creating invoice with ORM: %s", e)
        logger.error("Invoice data keys: %s", list(invoice_data.keys()))
        raise

    create_ar_entry_from_invoice(invoice)

    # Auto-send when the invoice is created already 'sent'
    if invoice.status == "sent":
        try:
            from .email_service import send_invoice_email
            from .invoice_pdf_html import generate_invoice_pdf_from_html

            pdf_content = generate_invoice_pdf_from_html(invoice)
            send_invoice_email(invoice, pdf_content)
        except Exception as e:
            from django.db import DatabaseError

            if isinstance(e, DatabaseError):
                raise
            logger.error("Failed to send invoice email: %s", e)

    return invoice


def revert_sales_order_to_draft(sales_order: SalesOrder, user) -> SalesOrder:
    """
    Staff: move issued / allocated / ready_for_shipment back to draft.
    Releases allocations and cancels draft invoices. Blocked if shipments or shipped qty.
    """
    from .sales_order_allocation_release import release_sales_order_allocations

    if not getattr(user, "is_staff", False):
        raise SellFlowError("Only staff can revert a sales order to draft.", status_code=403)

    if sales_order.status not in ("issued", "allocated", "ready_for_shipment"):
        raise SellFlowError(
            f"Only issued, allocated, or ready-for-shipment orders can be reverted. "
            f"Current status: {sales_order.status}"
        )

    if sales_order.shipments.exists():
        raise SellFlowError(
            "This order has checkout shipments. Reverse each shipment first, then revert to draft."
        )

    for item in sales_order.items.all():
        if float(item.quantity_shipped or 0) > 1e-6:
            raise SellFlowError(
                "This order has shipped quantities on file. Reverse shipments first, "
                "then revert to draft."
            )

    blocking = Invoice.objects.filter(sales_order=sales_order).exclude(
        status__in=("draft", "cancelled")
    )
    if blocking.exists():
        nums = ", ".join(blocking.values_list("invoice_number", flat=True)[:5])
        raise SellFlowError(
            f"Void non-draft invoices in Finance first (mark cancelled). Blocking: {nums}"
        )

    with transaction.atomic():
        release_sales_order_allocations(sales_order)
        Invoice.objects.filter(sales_order=sales_order, status="draft").update(status="cancelled")
        sales_order.status = "draft"
        sales_order.save(update_fields=["status"])

    sales_order.refresh_from_db()
    return sales_order


def reverse_sales_shipment(
    shipment_id: int, user, *, allow_non_draft_invoice: bool = False
) -> dict:
    """Staff wrapper around ``shipment_reversal.reverse_shipment``."""
    from .shipment_reversal import reverse_shipment

    if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
        raise SellFlowError("Only staff can reverse a shipment.", status_code=403)

    try:
        return reverse_shipment(
            int(shipment_id),
            allow_non_draft_invoice=allow_non_draft_invoice,
        )
    except ValueError as e:
        raise SellFlowError(str(e)) from e
