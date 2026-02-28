# Add dimensions and pieces to Shipment for packing list

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0054_invoiceitem_sales_order_item_and_total'),
    ]

    operations = [
        migrations.AddField(
            model_name='shipment',
            name='dimensions',
            field=models.CharField(blank=True, help_text='Pallet/box dimensions (e.g. 48x40x60)', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='shipment',
            name='pieces',
            field=models.PositiveIntegerField(blank=True, help_text='Number of boxes (ground) or pallets (FTL/LTL)', null=True),
        ),
    ]
