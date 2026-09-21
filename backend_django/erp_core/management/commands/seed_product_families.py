from django.core.management.base import BaseCommand

from erp_core.product_families import (
    backfill_item_product_families,
    seed_pigment_product_families,
)


class Command(BaseCommand):
    help = "Upsert pigment family letters A–Q and backfill Item.product_family from SKUs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only set product_family when currently blank.",
        )

    def handle(self, *args, **options):
        n_fam = seed_pigment_product_families()
        n_items = backfill_item_product_families(only_missing=options["only_missing"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Upserted {n_fam} pigment families; updated {n_items} item(s)."
            )
        )
