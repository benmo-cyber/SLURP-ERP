# Add expected_ship_date to Shipment for per-release on-time KPI

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0059_add_critical_control_point'),
    ]

    operations = [
        migrations.AddField(
            model_name='shipment',
            name='expected_ship_date',
            field=models.DateTimeField(
                blank=True,
                help_text='Agreed/due date for this release. Used for on-time KPI (compare to ship_date).',
                null=True
            ),
        ),
    ]
