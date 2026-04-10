"""
Regenerate LotCoaCustomerCopy PDFs for sales allocations (e.g. after master COA was added later).

  python manage.py sync_customer_coas
  python manage.py sync_customer_coas --so-number 1022
"""
from django.core.management.base import BaseCommand

from erp_core.coa_allocation import sync_customer_coa_for_sales_order_lot
from erp_core.models import SalesOrderLot


class Command(BaseCommand):
    help = 'Sync customer COA PDFs for SalesOrderLot rows (calls the same logic as allocation save).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--so-number',
            type=str,
            default='',
            help='Only allocations on this sales order number (e.g. 1022).',
        )

    def handle(self, *args, **options):
        so_number = (options.get('so_number') or '').strip()
        qs = SalesOrderLot.objects.select_related(
            'sales_order_item__sales_order',
        ).order_by('id')
        if so_number:
            qs = qs.filter(sales_order_item__sales_order__so_number=so_number)

        ids = list(qs.values_list('pk', flat=True))
        if not ids:
            self.stdout.write(self.style.WARNING('No SalesOrderLot rows matched.'))
            return

        for pk in ids:
            sync_customer_coa_for_sales_order_lot(int(pk))

        self.stdout.write(self.style.SUCCESS(f'Synced customer COAs for {len(ids)} allocation(s).'))
