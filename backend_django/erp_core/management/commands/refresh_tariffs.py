"""
Django management command to refresh tariff rates from Flexport
Can be run manually or scheduled (e.g., every Sunday at 2am)
"""
from django.core.management.base import BaseCommand
from erp_core.flexport_tariff import update_tariffs
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh tariff rates for all items with HTS codes and country of origin from Flexport Tariff Simulator'

    def handle(self, *args, **options):
        self.stdout.write('Starting tariff refresh from Flexport Tariff Simulator...')
        
        try:
            updated_count, error_count = update_tariffs()
            
            if error_count == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully updated {updated_count} tariff(s).'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Updated {updated_count} tariff(s). {error_count} error(s) occurred.'
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to refresh tariffs: {str(e)}')
            )
            logger.error(f'Tariff refresh command failed: {str(e)}')
            raise
