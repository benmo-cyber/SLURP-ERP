"""
Create journal entries for Accounts Payable rows that have none (e.g. after schema fix).

  python manage.py backfill_ap_journal_entries --dry-run
  python manage.py backfill_ap_journal_entries
"""

from django.core.management.base import BaseCommand

from erp_core.models import AccountsPayable
from erp_core.views import create_ap_journal_entry


class Command(BaseCommand):
    help = 'Attach GL journal entries to AP rows missing journal_entry_id.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry_run']
        qs = AccountsPayable.objects.filter(journal_entry__isnull=True)
        n = qs.count()
        if dry:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {n} AP rows have no journal entry.'))
            for ap in qs[:50]:
                self.stdout.write(f'  AP id={ap.id} PO={getattr(ap.purchase_order, "po_number", None)} {ap.vendor_name}')
            if n > 50:
                self.stdout.write(f'  ... and {n - 50} more')
            return

        ok = 0
        fail = 0
        for ap in qs.iterator():
            try:
                je = create_ap_journal_entry(ap)
                if je:
                    ap.journal_entry = je
                    ap.save(update_fields=['journal_entry', 'updated_at'])
                    ok += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'AP id={ap.id} -> JE {je.entry_number}')
                    )
                else:
                    fail += 1
                    self.stdout.write(self.style.WARNING(f'AP id={ap.id}: create_ap_journal_entry returned None'))
            except Exception as e:
                fail += 1
                self.stdout.write(self.style.ERROR(f'AP id={ap.id}: {e}'))

        self.stdout.write(f'Done: linked={ok}, skipped/failed={fail}')
