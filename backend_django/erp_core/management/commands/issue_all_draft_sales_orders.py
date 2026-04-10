"""
Set every sales order with status=draft to issued (same end state as POST /sales-orders/{id}/issue/).

  python manage.py issue_all_draft_sales_orders --dry-run
  python manage.py issue_all_draft_sales_orders
  python manage.py issue_all_draft_sales_orders --send-email   # also send SO confirmation PDF email per order
"""

from django.core.management.base import BaseCommand

from erp_core.models import SalesOrder


class Command(BaseCommand):
    help = 'Issue all sales orders that are still in draft status.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List draft SOs without changing them')
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='Send sales order confirmation email (with PDF) for each issued order. Default: skip.',
        )

    def handle(self, *args, **options):
        qs = SalesOrder.objects.filter(status='draft').order_by('id')
        n = qs.count()
        if n == 0:
            self.stdout.write(self.style.WARNING('No draft sales orders found.'))
            return

        if options['dry_run']:
            self.stdout.write(f'Would issue {n} draft sales order(s):')
            for so in qs:
                self.stdout.write(f'  {so.so_number}  id={so.id}  customer={so.customer_name or ""}')
            return

        issued = 0
        for so in qs:
            so.status = 'issued'
            so.save(update_fields=['status'])
            issued += 1
            self.stdout.write(self.style.SUCCESS(f'Issued {so.so_number} (id={so.id})'))

            if options['send_email']:
                try:
                    from erp_core.sales_order_pdf_html import generate_sales_order_pdf_from_html
                    from erp_core.email_service import send_sales_order_confirmation_email

                    pdf_content = generate_sales_order_pdf_from_html(so)
                    send_sales_order_confirmation_email(so, pdf_content)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  Email/PDF failed for {so.so_number}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Done. Issued {issued} sales order(s).'))
        if not options['send_email']:
            self.stdout.write('(Confirmation emails were not sent; use --send-email if you want them.)')
