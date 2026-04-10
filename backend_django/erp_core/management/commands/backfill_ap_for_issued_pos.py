"""
Align Accounts Payable with issued vendor purchase orders.

1) Creates a material AP line (same rules as PO receive) for each vendor PO that is
   issued/received/completed but has no AP rows at all, using PO order_date as invoice
   date and vendor payment terms for due date.

2) Optionally recalculates due_date from invoice_date + vendor profile payment terms
   for existing PO-linked AP (fixes rows where due was incorrectly set to invoice date).

Examples::

    python manage.py backfill_ap_for_issued_pos --dry-run
    python manage.py backfill_ap_for_issued_pos
    python manage.py backfill_ap_for_issued_pos --fix-due-dates all --no-create-missing
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from erp_core.models import PurchaseOrder, AccountsPayable
from erp_core.views import create_ap_entry_from_po, ap_due_date_from_invoice_and_vendor


def _po_monetary_total(po):
    t = float(po.total or 0)
    if t > 0:
        return round(t, 2)
    sub = sum(
        float(i.quantity_ordered or 0) * float(i.unit_price or 0)
        for i in po.items.all()
    )
    return round(sub, 2)


class Command(BaseCommand):
    help = 'Backfill material AP for issued vendor POs missing lines; fix PO-linked due dates from vendor terms.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show actions without saving.')
        parser.add_argument(
            '--no-create-missing',
            action='store_true',
            help='Do not create new material AP rows for POs with zero lines.',
        )
        parser.add_argument(
            '--fix-due-dates',
            choices=('none', 'same-as-invoice', 'all'),
            default='same-as-invoice',
            help=(
                'none: skip; same-as-invoice: only rows where due_date equals invoice_date; '
                'all: recalc every PO-linked AP line from terms.'
            ),
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        create_missing = not options['no_create_missing']
        fix_mode = options['fix_due_dates']

        if dry:
            self.stdout.write(self.style.WARNING('DRY RUN - no database writes.'))

        pos = (
            PurchaseOrder.objects.filter(po_type='vendor')
            .exclude(status__in=['draft', 'cancelled'])
            .prefetch_related('ap_entries', 'items')
        )

        created = 0
        skipped_zero = 0
        skipped_has_ap = 0

        if create_missing:
            for po in pos:
                if po.ap_entries.exists():
                    skipped_has_ap += 1
                    continue
                amt = _po_monetary_total(po)
                if amt <= 0:
                    skipped_zero += 1
                    self.stdout.write(
                        f'  Skip PO {po.po_number} ({po.status}): total is zero — add lines on PO or enter bills manually.'
                    )
                    continue
                inv_date = timezone.now().date()
                od = po.order_date
                if od is not None:
                    inv_date = od.date() if hasattr(od, 'date') else od
                if dry:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Would create material AP for PO {po.po_number} ({po.status}) '
                            f'amount={amt} invoice_date={inv_date}'
                        )
                    )
                    created += 1
                else:
                    ap = create_ap_entry_from_po(
                        po,
                        invoice_date=inv_date,
                        source_tag='backfill issued PO',
                    )
                    if ap:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Created material AP id={ap.id} for PO {po.po_number} ({po.status})'
                            )
                        )
                        created += 1
                    else:
                        self.stdout.write(self.style.ERROR(f'Could not create AP for PO {po.po_number}'))

        fixed_due = 0
        if fix_mode != 'none':
            aps = AccountsPayable.objects.filter(purchase_order__isnull=False).select_related(
                'purchase_order'
            )
            for ap in aps:
                new_due = ap_due_date_from_invoice_and_vendor(ap.invoice_date, ap.vendor_name)
                if new_due is None:
                    continue
                if fix_mode == 'same-as-invoice':
                    if ap.due_date != ap.invoice_date:
                        continue
                if ap.due_date == new_due:
                    continue
                po_num = ap.purchase_order.po_number if ap.purchase_order_id else ''
                if dry:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Would set AP id={ap.id} PO={po_num} due_date {ap.due_date} -> {new_due} '
                            f'(invoice_date={ap.invoice_date})'
                        )
                    )
                    fixed_due += 1
                else:
                    ap.due_date = new_due
                    ap.save(update_fields=['due_date', 'updated_at'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated AP id={ap.id} PO={po_num} due_date -> {new_due}'
                        )
                    )
                    fixed_due += 1

        self.stdout.write('')
        self.stdout.write(
            f'Summary: created={created}, POs skipped (already had AP)={skipped_has_ap}, '
            f'skipped (zero total)={skipped_zero}, due_date updates={fixed_due}'
        )
