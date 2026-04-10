# VendorContact job title / role field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0078_salesorder_order_date_editable'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorcontact',
            name='title',
            field=models.CharField(
                blank=True,
                help_text='Job title or role (e.g. Sales Manager, Logistics)',
                max_length=255,
                null=True,
            ),
        ),
    ]
