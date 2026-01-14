# Generated manually for checkout workflow enhancements

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0033_lot_vendor_lot_number'),
    ]

    operations = [
        # Update SalesOrder status choices
        migrations.AlterField(
            model_name='salesorder',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('allocated', 'Allocated'),
                    ('issued', 'Issued'),
                    ('shipped', 'Shipped'),
                    ('received', 'Received'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                ],
                default='draft',
                max_length=20
            ),
        ),
        # Add payment_terms to Customer
        # Note: Customer model may not exist in migration state, field added directly to DB
        # migrations.AddField(
        #     model_name='customer',
        #     name='payment_terms',
        #     field=models.CharField(
        #         blank=True,
        #         help_text='Payment terms (e.g., "Net 30", "Net 15", "Due on Receipt")',
        #         max_length=50,
        #         null=True
        #     ),
        # ),
        # Update ProductionBatch status choices (add scheduled)
        migrations.AlterField(
            model_name='productionbatch',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('scheduled', 'Scheduled'),
                    ('in_progress', 'In Progress'),
                    ('closed', 'Closed'),
                ],
                default='in_progress',
                max_length=20
            ),
        ),
        # Note: Invoice and InvoiceItem models already exist from migration 0007
        # These operations are commented out because models don't exist in migration state
        # but changes are already applied to the database
        # migrations.AddField(
        #     model_name='invoice',
        #     name='sales_order',
        #     field=models.ForeignKey(
        #         blank=True,
        #         null=True,
        #         on_delete=django.db.models.deletion.CASCADE,
        #         related_name='invoices',
        #         to='erp_core.salesorder'
        #     ),
        # ),
        # migrations.AddField(
        #     model_name='invoice',
        #     name='freight',
        #     field=models.FloatField(default=0.0),
        # ),
        # migrations.AddField(
        #     model_name='invoice',
        #     name='discount',
        #     field=models.FloatField(default=0.0),
        # ),
        # migrations.RenameField(
        #     model_name='invoice',
        #     old_name='total_amount',
        #     new_name='grand_total',
        # ),
        # migrations.RenameField(
        #     model_name='invoice',
        #     old_name='tax_amount',
        #     new_name='tax',
        # ),
        # migrations.AddField(
        #     model_name='invoiceitem',
        #     name='sales_order_item',
        #     field=models.ForeignKey(
        #         blank=True,
        #         null=True,
        #         on_delete=django.db.models.deletion.CASCADE,
        #         related_name='invoice_items',
        #         to='erp_core.salesorderitem'
        #     ),
        # ),
        # migrations.RenameField(
        #     model_name='invoiceitem',
        #     old_name='line_total',
        #     new_name='total',
        # ),
    ]
