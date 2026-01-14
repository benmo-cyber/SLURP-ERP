# Generated manually for SalesOrderLot table
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0039_add_logging_models'),
        ('erp_core', '0040_merge_logging'),
    ]

    operations = [
        migrations.CreateModel(
            name='SalesOrderLot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity_allocated', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('lot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales_order_allocations', to='erp_core.lot')),
                ('sales_order_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='allocated_lots', to='erp_core.salesorderitem')),
            ],
            options={
                'ordering': ['sales_order_item', 'lot'],
                'unique_together': {('sales_order_item', 'lot')},
            },
        ),
    ]
