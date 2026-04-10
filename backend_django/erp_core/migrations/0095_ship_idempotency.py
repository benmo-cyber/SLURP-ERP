import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0094_backfill_invoice_due_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShipIdempotency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, max_length=128, unique=True)),
                ('response_json', models.TextField(help_text='JSON body returned to the client')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sales_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ship_idempotencies', to='erp_core.salesorder')),
                ('shipment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='idempotency_records', to='erp_core.shipment')),
            ],
            options={
                'verbose_name_plural': 'Ship idempotency keys',
            },
        ),
    ]
