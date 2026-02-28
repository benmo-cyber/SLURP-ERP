# Add sales_order_item and rename line_total to total on InvoiceItem (align DB with full schema)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0053_add_bank_reconciliation'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoiceitem',
            name='sales_order_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name='invoice_items',
                to='erp_core.salesorderitem',
            ),
        ),
        migrations.RenameField(
            model_name='invoiceitem',
            old_name='line_total',
            new_name='total',
        ),
    ]
