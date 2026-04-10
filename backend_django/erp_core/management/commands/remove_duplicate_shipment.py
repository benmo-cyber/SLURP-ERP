"""
Remove an accidental duplicate shipment (e.g. double checkout).

  python manage.py remove_duplicate_shipment --so-number 1033 --keep oldest --dry-run
  python manage.py remove_duplicate_shipment --so-number 1033 --keep oldest

--keep oldest  → delete the newer shipment (higher id / later ship_date), keep the first.
--keep newest  → delete the older shipment.
"""

from django.core.management.base import BaseCommand, CommandError

from erp_core.models import SalesOrder, Shipment
from erp_core.shipment_reversal import reverse_shipment


class Command(BaseCommand):
    help = 'Reverse and delete a duplicate shipment row (inventory + draft invoice + AR/journal).'

    def add_arguments(self, parser):
        parser.add_argument('--so-number', type=str, default=None, help='Sales order number (e.g. 1033)')
        parser.add_argument('--shipment-id', type=int, default=None, help='Explicit shipment PK to remove')
        parser.add_argument(
            '--keep',
            choices=['oldest', 'newest'],
            default='oldest',
            help='Which physical shipment to keep (the other is removed). Default: oldest.',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--allow-non-draft-invoice',
            action='store_true',
            help='Allow removal even if the linked auto-invoice is not draft (dangerous).',
        )

    def handle(self, *args, **options):
        sid = options['shipment_id']
        if sid is None:
            so_num = (options['so_number'] or '').strip()
            if not so_num:
                raise CommandError('Provide --shipment-id or --so-number')
            try:
                so = SalesOrder.objects.get(so_number=so_num)
            except SalesOrder.DoesNotExist as e:
                raise CommandError(f'Sales order {so_num!r} not found') from e
            shipments = list(Shipment.objects.filter(sales_order=so).order_by('ship_date', 'id'))
            if len(shipments) < 2:
                raise CommandError(
                    f'Sales order {so_num} has {len(shipments)} shipment(s); need at least 2 to remove a duplicate.'
                )
            if options['keep'] == 'oldest':
                sid = shipments[-1].id
                self.stdout.write(f'Keeping oldest shipment id={shipments[0].id}, removing id={sid}')
            else:
                sid = shipments[0].id
                self.stdout.write(f'Keeping newest shipment id={shipments[-1].id}, removing id={sid}')

        result = reverse_shipment(
            sid,
            allow_non_draft_invoice=options['allow_non_draft_invoice'],
            dry_run=options['dry_run'],
        )
        self.stdout.write(str(result))
