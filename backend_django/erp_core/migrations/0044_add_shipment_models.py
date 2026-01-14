# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0043_add_issued_status_to_invoice'),
    ]

    operations = [
        migrations.CreateModel(
            name='Shipment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ship_date', models.DateTimeField(help_text='Date the shipment was shipped')),
                ('tracking_number', models.CharField(help_text='Tracking number for this shipment', max_length=255)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sales_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shipments', to='erp_core.salesorder')),
            ],
            options={
                'ordering': ['-ship_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ShipmentItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity_shipped', models.FloatField(help_text='Quantity shipped in this specific shipment')),
                ('sales_order_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shipment_items', to='erp_core.salesorderitem')),
                ('shipment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='erp_core.shipment')),
            ],
            options={
                'ordering': ['shipment', 'sales_order_item'],
            },
        ),
    ]
