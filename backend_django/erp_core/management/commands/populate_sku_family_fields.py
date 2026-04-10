"""
One-time (or repeatable) backfill: parse Item.sku into sku_parent_code / sku_pack_suffix,
link sku_parent_item to a master row when one exists. Skips indirect_material.

Usage:
  python manage.py populate_sku_family_fields
  python manage.py populate_sku_family_fields --dry-run
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from erp_core.models import Item
from erp_core.sku_family import apply_parsed_family_to_item, parse_sku_family


class Command(BaseCommand):
    help = 'Backfill sku_parent_code, sku_pack_suffix, and sku_parent_item from SKU rules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print actions without saving',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        qs = Item.objects.exclude(item_type='indirect_material')
        updated_parse = 0
        linked = 0

        for item in qs.iterator():
            parent, suffix = parse_sku_family(
                item.sku or '',
                product_category=item.product_category,
                item_type=item.item_type,
            )
            if not parent:
                continue
            if dry:
                self.stdout.write(f'Would set {item.sku!r} -> parent={parent!r} suffix={suffix!r}')
                updated_parse += 1
                continue

            if apply_parsed_family_to_item(item, commit=True):
                updated_parse += 1

        # Second pass: link children to master rows (same vendor preferred)
        children = Item.objects.exclude(item_type='indirect_material').exclude(
            Q(sku_pack_suffix__isnull=True) | Q(sku_pack_suffix='')
        )

        for item in children.iterator():
            code = (item.sku_parent_code or '').strip().upper()
            if not code:
                continue
            if item.sku_parent_item_id:
                continue

            masters = Item.objects.filter(
                sku__iexact=code,
            ).exclude(pk=item.pk).exclude(item_type='indirect_material').filter(
                Q(sku_pack_suffix__isnull=True) | Q(sku_pack_suffix='')
            )
            v = item.vendor or ''
            parent = None
            if v:
                parent = masters.filter(vendor=v).first()
            if not parent:
                parent = masters.filter(Q(vendor__isnull=True) | Q(vendor='')).first()
            if not parent:
                parent = masters.first()

            if not parent:
                if dry:
                    self.stdout.write(f'No master found for child {item.sku!r} (family {code})')
                continue

            if dry:
                self.stdout.write(f'Would link {item.sku!r} -> parent item id={parent.id} ({parent.sku})')
                linked += 1
                continue

            item.sku_parent_item = parent
            item.save(update_fields=['sku_parent_item'])
            linked += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Parsed/updated rows: {updated_parse}, parent links: {linked}'
                + (' (dry-run)' if dry else '')
            )
        )
