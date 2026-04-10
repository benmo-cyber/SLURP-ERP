from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0087_salesorder_ship_to_and_address_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='drop_ship',
            field=models.BooleanField(
                default=False,
                help_text='Vendor ships direct to customer; do not receive into inventory or allocate from stock.',
            ),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='drop_ship',
            field=models.BooleanField(
                default=False,
                help_text='Vendor ships direct to final destination; do not check in or mark received into stock.',
            ),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='fulfillment_sales_order',
            field=models.ForeignKey(
                blank=True,
                help_text='Sales order this drop-ship PO fulfills (ship-to copied from SO).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='drop_ship_purchase_orders',
                to='erp_core.salesorder',
            ),
        ),
    ]
