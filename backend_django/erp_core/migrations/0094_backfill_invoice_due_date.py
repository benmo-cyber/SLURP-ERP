# Backfill NULL invoice due_date using issue date + customer payment terms (same rule as Invoice.save).

from django.db import migrations

from erp_core.invoice_helpers import due_date_from_issue_and_payment_terms


def forwards(apps, schema_editor):
    Invoice = apps.get_model('erp_core', 'Invoice')
    SalesOrder = apps.get_model('erp_core', 'SalesOrder')
    CustomerContact = apps.get_model('erp_core', 'CustomerContact')
    Customer = apps.get_model('erp_core', 'Customer')

    qs = Invoice.objects.filter(due_date__isnull=True).filter(invoice_date__isnull=False)
    for inv in qs.iterator():
        terms = ''
        if inv.sales_order_id:
            so = SalesOrder.objects.filter(pk=inv.sales_order_id).first()
            if so and so.customer_id:
                c = Customer.objects.filter(pk=so.customer_id).first()
                if c:
                    terms = (c.payment_terms or '').strip()
        if not terms and inv.contact_id:
            cc = CustomerContact.objects.filter(pk=inv.contact_id).first()
            if cc and cc.customer_id:
                c = Customer.objects.filter(pk=cc.customer_id).first()
                if c:
                    terms = (c.payment_terms or '').strip()
        due = due_date_from_issue_and_payment_terms(inv.invoice_date, terms)
        if due:
            Invoice.objects.filter(pk=inv.pk).update(due_date=due)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0093_campaign_lot'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
