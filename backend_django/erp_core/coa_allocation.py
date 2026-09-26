"""Create/update customer-facing COA PDFs when lots are allocated to sales orders.

Issued PDFs are immutable: changing options creates a new current copy and keeps
the prior row for history.
"""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def sales_order_customer_display(sales_order) -> str:
    c = getattr(sales_order, "customer", None)
    if c is not None and getattr(c, "name", None):
        return (c.name or "").strip()
    return (getattr(sales_order, "customer_name", None) or "").strip()


def current_customer_coa(sales_order_lot):
    """Active (is_current) customer COA for an allocation, if any."""
    if sales_order_lot is None:
        return None
    qs = getattr(sales_order_lot, "coa_customer_copies", None)
    if qs is None:
        return None
    return qs.filter(is_current=True).order_by("-id").first()


def coa_quantity_for_sales_order_lot(sol) -> float:
    """
    Quantity printed on the customer COA for this allocation.

    Prefer live ``quantity_allocated``. After pickup that field is zeroed, so fall
    back to the last positive COA snapshot, then the SO line's shipped/ordered qty.
    Never invent a zero snapshot that would wipe a previously printed ship qty.
    """
    from .models import LotCoaCustomerCopy

    alloc = float(getattr(sol, "quantity_allocated", 0) or 0)
    if alloc > 1e-6:
        return alloc

    prior = (
        LotCoaCustomerCopy.objects.filter(sales_order_lot_id=sol.pk)
        .filter(quantity_snapshot__gt=0)
        .order_by("-id")
        .values_list("quantity_snapshot", flat=True)
        .first()
    )
    if prior is not None and float(prior) > 1e-6:
        return float(prior)

    line = getattr(sol, "sales_order_item", None)
    if line is not None:
        shipped = float(getattr(line, "quantity_shipped", 0) or 0)
        if shipped > 1e-6:
            return shipped
        ordered = float(getattr(line, "quantity_ordered", 0) or 0)
        if ordered > 1e-6:
            return ordered
    return 0.0


def _default_coa_basis(lot) -> tuple[str, object | None]:
    """Return (basis, campaign_cert_or_None). Prefer campaign when available."""
    from .campaign_coa import current_campaign_coa, lot_campaign

    camp = lot_campaign(lot)
    if camp is None:
        return "batch", None
    camp_cert = current_campaign_coa(camp)
    if camp_cert is None:
        return "batch", None
    return "campaign", camp_cert


def _sync_customer_coa_impl(sales_order_lot_id: int) -> None:
    from .models import LotCoaCertificate, LotCoaCustomerCopy, SalesOrderLot
    from .coa_customer_options import apply_customer_coa_item_defaults
    from .coa_pdf_html import save_customer_copy_coa_pdf

    try:
        sol = SalesOrderLot.objects.select_related(
            "lot__item",
            "sales_order_item__sales_order__customer",
        ).get(pk=sales_order_lot_id)
    except SalesOrderLot.DoesNotExist:
        return

    lot = sol.lot
    try:
        cert = (
            LotCoaCertificate.objects.select_related("lot__item")
            .prefetch_related("line_results", "lot__item__coa_test_lines")
            .get(lot_id=lot.id)
        )
    except LotCoaCertificate.DoesNotExist:
        LotCoaCustomerCopy.objects.filter(sales_order_lot_id=sales_order_lot_id).delete()
        return

    so = sol.sales_order_item.sales_order
    cust = sales_order_customer_display(so)[:255]
    po = (getattr(so, "customer_reference_number", None) or "").strip()[:120]
    qty = coa_quantity_for_sales_order_lot(sol)
    basis, camp_cert = _default_coa_basis(lot)

    with transaction.atomic():
        copy = current_customer_coa(sol)
        if not copy:
            copy = LotCoaCustomerCopy(
                sales_order_lot=sol,
                certificate=cert,
                is_current=True,
                coa_basis=basis,
                campaign_certificate=camp_cert,
                customer_name=cust,
                customer_po=po,
                quantity_snapshot=qty,
            )
            apply_customer_coa_item_defaults(copy, cert, force=True)
            copy.save()
            save_customer_copy_coa_pdf(copy)
            return

        # Immutable once PDF exists: spawn a new current copy when master data shifts.
        needs_new = bool(copy.coa_pdf) and (
            copy.certificate_id != cert.id
            or (copy.coa_basis or "batch") != basis
            or (copy.campaign_certificate_id or None)
            != (camp_cert.id if camp_cert else None)
            or abs(float(copy.quantity_snapshot or 0) - qty) > 1e-6
        )
        if needs_new:
            LotCoaCustomerCopy.objects.filter(pk=copy.pk).update(is_current=False)
            new_copy = LotCoaCustomerCopy(
                sales_order_lot=sol,
                certificate=cert,
                is_current=True,
                coa_basis=basis,
                campaign_certificate=camp_cert,
                customer_name=cust,
                customer_po=po,
                quantity_snapshot=qty,
                included_line_result_ids=list(copy.included_line_result_ids or []),
                include_qc_row=copy.include_qc_row,
                result_display_mode=copy.result_display_mode,
                line_display_overrides=dict(copy.line_display_overrides or {}),
                customization_saved=copy.customization_saved,
            )
            if not new_copy.customization_saved:
                apply_customer_coa_item_defaults(new_copy, cert, force=True)
            new_copy.save()
            save_customer_copy_coa_pdf(new_copy)
            return

        # Draft / no PDF yet — safe to update in place.
        copy.certificate_id = cert.id
        copy.customer_name = cust
        copy.customer_po = po
        copy.quantity_snapshot = qty
        copy.coa_basis = basis
        copy.campaign_certificate = camp_cert
        if not copy.customization_saved:
            apply_customer_coa_item_defaults(copy, cert, force=False)
        copy.save()
        if not copy.coa_pdf:
            save_customer_copy_coa_pdf(copy)


def sync_customer_coa_for_sales_order_lot(sales_order_lot_id: int) -> None:
    try:
        _sync_customer_coa_impl(sales_order_lot_id)
    except Exception:
        logger.exception(
            "sync_customer_coa_for_sales_order_lot failed for sol_id=%s",
            sales_order_lot_id,
        )


def sync_customer_coas_for_lot(lot_id: int) -> None:
    from .models import SalesOrderLot

    so_ids = set()
    for sol in SalesOrderLot.objects.filter(lot_id=lot_id).select_related(
        "sales_order_item"
    ):
        sync_customer_coa_for_sales_order_lot(sol.id)
        so_id = getattr(sol.sales_order_item, "sales_order_id", None)
        if so_id:
            so_ids.add(so_id)
    for so_id in so_ids:
        consolidate_customer_coas_for_sales_order(so_id)


def consolidate_customer_coas_for_sales_order(sales_order_or_id) -> list:
    """
    Collapse campaign-member customer COAs on one SO into a single PDF per campaign.

    Returns the ordered list of *display* current copies:
    - one per campaign (qty = sum of campaign allocations on this SO)
    - one per non-campaign allocation
    """
    from .models import LotCoaCustomerCopy, SalesOrder, SalesOrderLot
    from .coa_pdf_html import save_customer_copy_coa_pdf

    if hasattr(sales_order_or_id, "pk"):
        so = sales_order_or_id
        so_id = so.pk
    else:
        so_id = int(sales_order_or_id)
        so = SalesOrder.objects.filter(pk=so_id).first()
    if not so_id:
        return []

    sols = list(
        SalesOrderLot.objects.filter(sales_order_item__sales_order_id=so_id)
        .select_related("lot", "sales_order_item")
        .prefetch_related("coa_customer_copies")
        .order_by("id")
    )
    # Ensure each SOL has a current copy when a master exists.
    for sol in sols:
        if current_customer_coa(sol) is None:
            sync_customer_coa_for_sales_order_lot(sol.id)

    sols = list(
        SalesOrderLot.objects.filter(sales_order_item__sales_order_id=so_id)
        .select_related("lot", "sales_order_item")
        .prefetch_related("coa_customer_copies")
        .order_by("id")
    )

    campaign_groups: dict[int, dict] = {}
    batch_copies = []
    for sol in sols:
        copy = current_customer_coa(sol)
        if not copy:
            continue
        basis = (copy.coa_basis or "batch").strip().lower()
        camp_id = copy.campaign_certificate_id
        qty = coa_quantity_for_sales_order_lot(sol)
        if basis == "campaign" and camp_id:
            g = campaign_groups.get(camp_id)
            if not g:
                campaign_groups[camp_id] = {
                    "lead": copy,
                    "qty": 0.0,
                    "other_ids": [],
                }
                g = campaign_groups[camp_id]
            elif copy.id < g["lead"].id:
                g["other_ids"].append(g["lead"].id)
                g["lead"] = copy
            else:
                g["other_ids"].append(copy.id)
            g["qty"] += qty
        else:
            batch_copies.append(copy)

    display = []
    with transaction.atomic():
        for camp_id, g in campaign_groups.items():
            lead = (
                LotCoaCustomerCopy.objects.select_related(
                    "certificate__lot__item",
                    "campaign_certificate__campaign",
                    "sales_order_lot__lot",
                ).get(pk=g["lead"].id)
            )
            total = float(g["qty"] or 0)
            # Demote sibling campaign copies so UI/PDF only surface the lead.
            if g["other_ids"]:
                LotCoaCustomerCopy.objects.filter(id__in=g["other_ids"]).update(
                    is_current=False
                )
            needs_pdf = (
                abs(float(lead.quantity_snapshot or 0) - total) > 1e-6
                or not lead.coa_pdf
            )
            if abs(float(lead.quantity_snapshot or 0) - total) > 1e-6:
                # Immutable once PDF exists — spawn a new lead with rolled-up qty.
                if lead.coa_pdf:
                    LotCoaCustomerCopy.objects.filter(pk=lead.pk).update(is_current=False)
                    lead = LotCoaCustomerCopy.objects.create(
                        sales_order_lot=lead.sales_order_lot,
                        certificate=lead.certificate,
                        is_current=True,
                        coa_basis="campaign",
                        campaign_certificate_id=camp_id,
                        customer_name=lead.customer_name,
                        customer_po=lead.customer_po,
                        quantity_snapshot=total,
                        included_line_result_ids=list(
                            lead.included_line_result_ids or []
                        ),
                        include_qc_row=lead.include_qc_row,
                        result_display_mode=lead.result_display_mode,
                        line_display_overrides=dict(
                            lead.line_display_overrides or {}
                        ),
                        customization_saved=lead.customization_saved,
                    )
                    needs_pdf = True
                else:
                    lead.quantity_snapshot = total
                    lead.save(update_fields=["quantity_snapshot", "updated_at"])
            if needs_pdf:
                save_customer_copy_coa_pdf(lead)
            display.append(lead)

        display.extend(batch_copies)

    # Stable order: campaign leads first (by id), then batch.
    display.sort(
        key=lambda c: (
            0 if (c.coa_basis or "") == "campaign" else 1,
            c.id,
        )
    )
    return display


def customer_coa_docs_for_sales_order(sales_order) -> list:
    """
    COA buttons for an SO: consolidated campaign + batch customer copies.
    Falls back to master certs only when no customer copy exists yet.
    """
    return consolidate_customer_coas_for_sales_order(sales_order)


def customer_coa_button_label(copy) -> str:
    """Short label for workqueue / detail COA buttons."""
    basis = (getattr(copy, "coa_basis", None) or "batch").strip().lower()
    if basis == "campaign":
        camp = getattr(copy, "campaign_certificate", None)
        code = ""
        if camp is not None:
            c = getattr(camp, "campaign", None)
            code = (getattr(c, "campaign_code", None) or "") if c else ""
            if not code:
                code = (getattr(camp, "campaign_code", None) or "")
        return f"COA · {code}" if code else "COA · Campaign"
    lot = getattr(getattr(copy, "sales_order_lot", None), "lot", None)
    ln = (getattr(lot, "lot_number", None) or "").strip()
    return f"COA · {ln}" if ln else "COA"
