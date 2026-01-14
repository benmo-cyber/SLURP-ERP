# Generated migration for adding ready_for_shipment status and tracking_number
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0041_add_salesorderlot_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='tracking_number',
            field=models.CharField(blank=True, help_text='Shipping tracking number', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='salesorder',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('allocated', 'Allocated'),
                    ('ready_for_shipment', 'Ready for Shipment'),
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
    ]
