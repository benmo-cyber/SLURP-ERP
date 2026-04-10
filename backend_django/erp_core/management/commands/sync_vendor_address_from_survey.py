"""
Copy facility address from SupplierSurvey JSON onto Vendor fields when Vendor address is empty.

  python manage.py sync_vendor_address_from_survey
  python manage.py sync_vendor_address_from_survey --dry-run
"""
from django.core.management.base import BaseCommand

from erp_core.models import Vendor
from erp_core.vendor_address_display import sync_survey_address_to_vendor


class Command(BaseCommand):
    help = 'Copy address from SupplierSurvey JSON to Vendor when vendor address columns are empty.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show how many would update without saving.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        updated = 0
        for v in Vendor.objects.select_related('survey').order_by('name'):
            if sync_survey_address_to_vendor(v, dry_run=dry_run):
                if not dry_run:
                    self.stdout.write(self.style.SUCCESS(f'{v.name} (id={v.id}): address synced from survey'))
                updated += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: would update {updated} vendor(s).'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Updated {updated} vendor(s).'))
