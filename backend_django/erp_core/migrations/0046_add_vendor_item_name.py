# Generated manually to add vendor_item_name field to Item model
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0045_add_repack_transaction_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='vendor_item_name',
            field=models.CharField(blank=True, help_text='Vendor Item Name - used in purchase orders to vendors', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='name',
            field=models.CharField(help_text='WWI Item Name - used for sales orders and internal reference', max_length=255),
        ),
    ]
