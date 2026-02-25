# Fix migration state: LotTransactionLog is missing before 0045 alters it.
# State-only; no database operations.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0044_add_shipment_models'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='LotTransactionLog',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('lot_number', models.CharField(db_index=True, help_text='Snapshot of lot number at time of transaction', max_length=20)),
                        ('item_sku', models.CharField(db_index=True, help_text='Item SKU at time of transaction', max_length=255)),
                        ('item_name', models.CharField(help_text='Item name at time of transaction', max_length=255)),
                        ('vendor', models.CharField(blank=True, help_text='Vendor at time of transaction', max_length=255, null=True)),
                        ('transaction_type', models.CharField(choices=[('receipt', 'Receipt'), ('production_input', 'Production Input'), ('production_output', 'Production Output'), ('repack_input', 'Repack Input'), ('repack_output', 'Repack Output'), ('sale', 'Sale'), ('adjustment', 'Adjustment'), ('allocation', 'Allocation'), ('deallocation', 'Deallocation'), ('manual', 'Manual'), ('reversal', 'Reversal/Cancellation')], help_text='Type of transaction', max_length=20)),
                        ('quantity_before', models.FloatField(help_text='Quantity remaining before this transaction')),
                        ('quantity_change', models.FloatField(help_text='Quantity change (positive for additions, negative for reductions)')),
                        ('quantity_after', models.FloatField(help_text='Quantity remaining after this transaction')),
                        ('unit_of_measure', models.CharField(choices=[('lbs', 'Pounds'), ('kg', 'Kilograms'), ('ea', 'Each')], default='lbs', help_text='Unit of measure for quantities', max_length=10)),
                        ('reference_number', models.CharField(blank=True, help_text='Batch number, SO number, PO number, etc.', max_length=100, null=True)),
                        ('reference_type', models.CharField(blank=True, help_text='Type of reference (batch_number, so_number, po_number, etc.)', max_length=50, null=True)),
                        ('transaction_id', models.IntegerField(blank=True, help_text='Related InventoryTransaction ID if applicable', null=True)),
                        ('batch_id', models.IntegerField(blank=True, help_text='Related ProductionBatch ID if applicable', null=True)),
                        ('sales_order_id', models.IntegerField(blank=True, help_text='Related SalesOrder ID if applicable', null=True)),
                        ('purchase_order_id', models.IntegerField(blank=True, help_text='Related PurchaseOrder ID if applicable', null=True)),
                        ('notes', models.TextField(blank=True, help_text='Additional context about the transaction', null=True)),
                        ('logged_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                        ('logged_by', models.CharField(blank=True, help_text='User who performed the transaction', max_length=255, null=True)),
                        ('lot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaction_logs', to='erp_core.lot')),
                    ],
                    options={
                        'ordering': ['-logged_at'],
                        'verbose_name': 'Lot Transaction Log',
                        'verbose_name_plural': 'Lot Transaction Logs',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
