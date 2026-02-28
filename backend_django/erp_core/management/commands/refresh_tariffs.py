"""
Django management command: tariff refresh (no-op).
Flexport HTS integration was removed; tariffs are entered manually in Cost Master.
This command is kept so existing schedules/cron do not error.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'No-op: Flexport integration removed. Enter tariffs manually in Cost Master.'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                'Tariff refresh from Flexport has been removed. Enter tariff rates manually in Cost Master (Finance or item/cost screens).'
            )
        )