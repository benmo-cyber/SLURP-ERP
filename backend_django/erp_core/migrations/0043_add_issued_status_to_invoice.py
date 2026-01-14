# Generated migration for adding issued status to Invoice
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0042_add_ready_for_shipment_status_and_tracking'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('issued', 'Issued'),
                    ('sent', 'Sent'),
                    ('paid', 'Paid'),
                    ('overdue', 'Overdue'),
                    ('cancelled', 'Cancelled'),
                ],
                default='draft',
                max_length=20
            ),
        ),
    ]
