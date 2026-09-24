"""RMA dock check-in: create staging -R lots forced on hold (customer_return)."""
from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

from .models import CustomerRma, CustomerRmaLine, InventoryTransaction, Lot
from .sell_services import SellFlowError


def next_staging_lot_number(source_lot_number: str) -> str:
    """Unique lot number `{orig}-R`, `{orig}-R2`, … within Lot.lot_number max_length=20."""
    base = (source_lot_number or "LOT").strip() or "LOT"
    for i in range(0, 99):
        suffix = "-R" if i == 0 else f"-R{i + 1}"
        room = 20 - len(suffix)
        if room < 1:
            suffix = suffix[:19]
            room = 20 - len(suffix)
        candidate = (base[:room] + suffix)[:20]
        if not Lot.objects.filter(lot_number=candidate).exists():
            return candidate
    raise SellFlowError(f"Could not allocate a staging lot number for {source_lot_number}.")


def check_in_rma_line(
    rma_line: CustomerRmaLine,
    *,
    quantity: float,
    user=None,
    freight_actual: Optional[float] = None,
    notes: str = "",
) -> Lot:
    """
    Receive qty against an open RMA line into a new staging lot on hold.
    Always creates hold kind=customer_return.
    """
    from .hold_services import ensure_open_hold_case
    from .rma_services import refresh_rma_receive_status
    from .views import log_lot_transaction

    qty = round(float(quantity), 2)
    if qty <= 0:
        raise SellFlowError("Check-in quantity must be positive.")

    rma = rma_line.rma
    if rma.status in ("cancelled", "closed"):
        raise SellFlowError(f"RMA {rma.rma_number} is {rma.status}.")

    open_qty = float(rma_line.quantity_open)
    if qty > open_qty + 1e-6:
        raise SellFlowError(
            f"Only {open_qty:.2f} remaining to receive on this RMA line "
            f"(requested {rma_line.quantity_requested})."
        )

    source = rma_line.source_lot
    actor = getattr(user, "username", None) or "system"
    freight = None
    if freight_actual is not None and str(freight_actual).strip() != "":
        try:
            freight = float(freight_actual)
        except (TypeError, ValueError) as e:
            raise SellFlowError("Invalid freight amount.") from e
        if freight < 0:
            raise SellFlowError("Freight cannot be negative.")

    with transaction.atomic():
        staging_number = next_staging_lot_number(source.lot_number or str(source.id))
        staging = Lot.objects.create(
            lot_number=staging_number,
            vendor_lot_number=source.vendor_lot_number,
            item=source.item,
            pack_size=source.pack_size,
            quantity=qty,
            quantity_remaining=qty,
            received_date=timezone.now(),
            manufacture_date=source.manufacture_date,
            expiration_date=source.expiration_date,
            status="on_hold",
            on_hold=True,
            quantity_on_hold=qty,
            freight_actual=freight,
            rma_number=rma.rma_number,
            source_lot=source,
            short_reason=f"RMA {rma.rma_number} return staging"[:255],
        )
        txn = InventoryTransaction.objects.create(
            transaction_type="return",
            lot=staging,
            quantity=qty,
            reference_number=rma.rma_number,
            notes=(
                f"RMA check-in from SO {rma.sales_order.so_number} "
                f"(source lot {source.lot_number})"
                + (f": {notes}" if (notes or "").strip() else "")
            ),
        )
        log_lot_transaction(
            lot=staging,
            quantity_before=0.0,
            quantity_change=qty,
            transaction_type="return",
            reference_number=rma.rma_number,
            reference_type="rma_number",
            transaction_id=txn.id,
            sales_order_id=rma.sales_order_id,
            notes=f"RMA check-in by {actor}",
        )
        ensure_open_hold_case(
            staging,
            user=user,
            kind="customer_return",
            summary=f"RMA {rma.rma_number} — customer return investigation"[:255],
            initial_note=(
                f"Checked in against RMA {rma.rma_number} / SO {rma.sales_order.so_number}. "
                f"Source lot {source.lot_number}. Qty {qty}."
                + (f"\n{(notes or '').strip()}" if (notes or "").strip() else "")
            ),
        )
        rma_line.quantity_received = round(
            float(rma_line.quantity_received or 0) + qty, 2
        )
        rma_line.staging_lot = staging
        rma_line.save(update_fields=["quantity_received", "staging_lot"])
        refresh_rma_receive_status(rma)

    return staging


def check_in_rma_lines(
    rma: CustomerRma,
    line_payloads: list[dict[str, Any]],
    *,
    user=None,
    freight_actual: Optional[float] = None,
    notes: str = "",
) -> list[Lot]:
    """
    Batch check-in. ``line_payloads``: [{rma_line_id, quantity}, ...]
    Freight applies to each staging lot when provided (same as optional PO freight).
    """
    lots = []
    with transaction.atomic():
        for raw in line_payloads:
            try:
                line_id = int(raw.get("rma_line_id") or raw.get("line_id"))
                qty = float(raw.get("quantity") or 0)
            except (TypeError, ValueError) as e:
                raise SellFlowError("Invalid RMA check-in line.") from e
            if qty <= 0:
                continue
            try:
                line = CustomerRmaLine.objects.select_related(
                    "rma__sales_order", "source_lot__item", "source_lot__pack_size"
                ).get(pk=line_id, rma=rma)
            except CustomerRmaLine.DoesNotExist as e:
                raise SellFlowError(f"RMA line {line_id} not found.") from e
            lots.append(
                check_in_rma_line(
                    line,
                    quantity=qty,
                    user=user,
                    freight_actual=freight_actual,
                    notes=notes,
                )
            )
    if not lots:
        raise SellFlowError("Enter a quantity greater than 0 on at least one line.")
    return lots
