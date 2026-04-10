import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from erp_core.models import SalesOrderLot, SupplierSurvey
from erp_core.vendor_address_display import sync_survey_address_to_vendor

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SupplierSurvey)
def supplier_survey_save_sync_vendor_address(sender, instance, **kwargs):
    """When questionnaire JSON is saved, copy address onto Vendor if profile columns are still empty."""
    try:
        sync_survey_address_to_vendor(instance.vendor, dry_run=False)
    except Exception:
        logger.exception(
            'sync_survey_address_to_vendor failed for survey id=%s vendor_id=%s',
            instance.pk,
            getattr(instance, 'vendor_id', None),
        )


@receiver(post_save, sender=SalesOrderLot)
def sales_order_lot_post_save_customer_coa(sender, instance, **kwargs):
    """When a lot is allocated to a sales order line, create/update customer COA PDF if the lot has a master COA."""
    from erp_core.coa_allocation import sync_customer_coa_for_sales_order_lot

    try:
        sync_customer_coa_for_sales_order_lot(instance.pk)
    except Exception:
        logger.exception('sync_customer_coa_for_sales_order_lot failed for SalesOrderLot id=%s', instance.pk)


@receiver(post_delete, sender=SalesOrderLot)
def sales_order_lot_post_delete_customer_coa(sender, instance, **kwargs):
    from erp_core.models import LotCoaCustomerCopy

    LotCoaCustomerCopy.objects.filter(sales_order_lot_id=instance.pk).delete()
