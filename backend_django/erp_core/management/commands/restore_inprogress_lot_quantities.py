"""
One-time fix: Add back to each lot the quantity that was deducted at batch create
for in_progress batches. We now only deduct when a batch is closed, so lots that
were already reduced need this quantity restored to avoid double-subtracting in
the inventory "Available" calculation.

Run once after deploying the change that stops reducing lots at batch create:
  python manage.py restore_inprogress_lot_quantities
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum
from erp_core.models import ProductionBatchInput, Lot


class Command(BaseCommand):
    help = 'Restore lot quantity_remaining for in-progress batch inputs (one-time migration).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write('DRY RUN - no changes will be saved.')

        # Sum quantity_used per lot for in_progress batches
        in_progress_totals = (
            ProductionBatchInput.objects
            .filter(batch__status='in_progress')
            .values('lot_id')
            .annotate(total=Sum('quantity_used'))
        )
        updated = 0
        for row in in_progress_totals:
            lot_id = row['lot_id']
            add_back = row['total'] or 0
            if add_back <= 0:
                continue
            try:
                lot = Lot.objects.get(id=lot_id)
                new_remaining = round(lot.quantity_remaining + add_back, 2)
                self.stdout.write(
                    f'Lot id={lot_id} {lot.lot_number}: {lot.quantity_remaining} -> {new_remaining} (+{add_back})'
                )
                if not dry_run:
                    lot.quantity_remaining = new_remaining
                    lot.save()
                updated += 1
            except Lot.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Lot id={lot_id} not found, skip.'))

        self.stdout.write(self.style.SUCCESS(f'Updated {updated} lot(s).'))
