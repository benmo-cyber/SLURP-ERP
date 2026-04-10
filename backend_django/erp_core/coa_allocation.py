"""Create/update customer-facing COA PDFs when lots are allocated to sales orders."""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def sales_order_customer_display(sales_order) -> str:
    c = getattr(sales_order, "customer", None)
    if c is not None and getattr(c, "name", None):
        return (c.name or "").strip()
    return (getattr(sales_order, "customer_name", None) or "").strip()


def _sync_customer_coa_impl(sales_order_lot_id: int) -> None:
    from .models import LotCoaCertificate, LotCoaCustomerCopy, SalesOrderLot
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
        cert = lot.coa_certificate
    except LotCoaCertificate.DoesNotExist:
        LotCoaCustomerCopy.objects.filter(sales_order_lot_id=sales_order_lot_id).delete()
        return

    so = sol.sales_order_item.sales_order
    cust = sales_order_customer_display(so)[:255]
    po = (getattr(so, "customer_reference_number", None) or "").strip()[:120]
    qty = float(sol.quantity_allocated or 0)

    with transaction.atomic():
        copy = LotCoaCustomerCopy.objects.filter(sales_order_lot=sol).first()
        if not copy:
            copy = LotCoaCustomerCopy(
                sales_order_lot=sol,
                certificate=cert,
                customer_name=cust,
                customer_po=po,
                quantity_snapshot=qty,
            )
            copy.save()
        else:
            copy.certificate_id = cert.id
            copy.customer_name = cust
            copy.customer_po = po
            copy.quantity_snapshot = qty
            copy.save(update_fields=["certificate", "customer_name", "customer_po", "quantity_snapshot", "updated_at"])

    try:
        save_customer_copy_coa_pdf(copy)
    except Exception:
        logger.exception("save_customer_copy_coa_pdf failed for LotCoaCustomerCopy id=%s", copy.pk)


def sync_customer_coa_for_sales_order_lot(sales_order_lot_id: int) -> None:
    """Schedule sync after commit when inside an outer transaction (e.g. save allocations)."""
    conn = transaction.get_connection()
    if conn.in_atomic_block:
        transaction.on_commit(lambda: _sync_customer_coa_impl(sales_order_lot_id))
    else:
        _sync_customer_coa_impl(sales_order_lot_id)


def sync_customer_coas_for_lot(lot_id: int) -> None:
    """Regenerate customer COAs for every sales allocation of this lot (e.g. after master COA is first created)."""
    from .models import SalesOrderLot

    for pk in SalesOrderLot.objects.filter(lot_id=lot_id).values_list('pk', flat=True):
        sync_customer_coa_for_sales_order_lot(int(pk))
