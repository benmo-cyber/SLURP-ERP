# Generated manually due to migration dependency issue
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0038_salesorder_ship_to_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrderLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('po_number', models.CharField(db_index=True, help_text='PO number at time of log', max_length=100)),
                ('action', models.CharField(choices=[('created', 'Created'), ('updated', 'Updated'), ('check_in', 'Check-In'), ('partial_check_in', 'Partial Check-In'), ('cancelled', 'Cancelled'), ('completed', 'Completed')], max_length=20)),
                ('vendor_name', models.CharField(blank=True, max_length=255, null=True)),
                ('vendor_customer_name', models.CharField(blank=True, max_length=255, null=True)),
                ('po_date', models.DateTimeField(blank=True, null=True)),
                ('required_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(blank=True, max_length=50, null=True)),
                ('carrier', models.CharField(blank=True, max_length=255, null=True)),
                ('po_received_date', models.DateTimeField(blank=True, help_text='PO received date at time of log', null=True)),
                ('lot_number', models.CharField(blank=True, help_text='Lot number if this is a check-in', max_length=20, null=True)),
                ('item_sku', models.CharField(blank=True, help_text='Item SKU if this is a check-in', max_length=255, null=True)),
                ('item_name', models.CharField(blank=True, help_text='Item name if this is a check-in', max_length=255, null=True)),
                ('quantity_received', models.FloatField(blank=True, help_text='Quantity received in this check-in', null=True)),
                ('received_date', models.DateTimeField(blank=True, help_text='Date lot was received', null=True)),
                ('total_items', models.IntegerField(default=0, help_text='Total number of items in PO')),
                ('total_quantity_ordered', models.FloatField(default=0.0, help_text='Total quantity ordered')),
                ('total_quantity_received', models.FloatField(default=0.0, help_text='Total quantity received at time of log')),
                ('notes', models.TextField(blank=True, help_text='Additional context', null=True)),
                ('logged_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('logged_by', models.CharField(blank=True, help_text='User who performed the action', max_length=255, null=True)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='erp_core.purchaseorder')),
            ],
            options={
                'verbose_name': 'Purchase Order Log',
                'verbose_name_plural': 'Purchase Order Logs',
                'ordering': ['-logged_at'],
            },
        ),
        migrations.CreateModel(
            name='ProductionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('batch_number', models.CharField(db_index=True, help_text='Batch number at time of closure', max_length=100)),
                ('batch_type', models.CharField(help_text='production or repack', max_length=20)),
                ('finished_good_sku', models.CharField(db_index=True, max_length=255)),
                ('finished_good_name', models.CharField(max_length=255)),
                ('quantity_produced', models.FloatField(help_text='Planned quantity')),
                ('quantity_actual', models.FloatField(help_text='Actual quantity produced')),
                ('variance', models.FloatField(default=0.0)),
                ('wastes', models.FloatField(default=0.0)),
                ('spills', models.FloatField(default=0.0)),
                ('production_date', models.DateTimeField(help_text='When batch was produced')),
                ('closed_date', models.DateTimeField(help_text='When batch was closed')),
                ('input_materials', models.TextField(blank=True, help_text='JSON string of input materials used', null=True)),
                ('input_lots', models.TextField(blank=True, help_text='JSON string of input lot numbers', null=True)),
                ('output_lot_number', models.CharField(blank=True, max_length=20, null=True)),
                ('output_quantity', models.FloatField(blank=True, null=True)),
                ('qc_parameters', models.TextField(blank=True, null=True)),
                ('qc_actual', models.TextField(blank=True, null=True)),
                ('qc_initials', models.CharField(blank=True, max_length=255, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('closed_by', models.CharField(blank=True, help_text='User who closed the batch', max_length=255, null=True)),
                ('logged_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='erp_core.productionbatch')),
            ],
            options={
                'verbose_name': 'Production Log',
                'verbose_name_plural': 'Production Logs',
                'ordering': ['-logged_at'],
            },
        ),
        migrations.AddIndex(
            model_name='purchaseorderlog',
            index=models.Index(fields=['-logged_at', 'po_number'], name='erp_core_p_logged__idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlog',
            index=models.Index(fields=['vendor_name', '-logged_at'], name='erp_core_p_vendor__idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlog',
            index=models.Index(fields=['action', '-logged_at'], name='erp_core_p_action__idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderlog',
            index=models.Index(fields=['lot_number', '-logged_at'], name='erp_core_p_lot_num_idx'),
        ),
        migrations.AddIndex(
            model_name='productionlog',
            index=models.Index(fields=['-logged_at', 'batch_number'], name='erp_core_p_logged__idx'),
        ),
        migrations.AddIndex(
            model_name='productionlog',
            index=models.Index(fields=['finished_good_sku', '-logged_at'], name='erp_core_p_finishe_idx'),
        ),
        migrations.AddIndex(
            model_name='productionlog',
            index=models.Index(fields=['closed_date', '-logged_at'], name='erp_core_p_closed__idx'),
        ),
    ]
