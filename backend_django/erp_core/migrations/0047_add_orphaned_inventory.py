# Generated manually to add orphaned inventory models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0046_add_vendor_item_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrphanedInventory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_item_sku', models.CharField(db_index=True, help_text='SKU of the deleted item', max_length=255)),
                ('original_item_name', models.CharField(help_text='Name of the deleted item', max_length=255)),
                ('original_item_vendor', models.CharField(blank=True, help_text='Vendor of the deleted item', max_length=255, null=True)),
                ('original_item_type', models.CharField(help_text='Item type of the deleted item', max_length=50)),
                ('original_item_unit', models.CharField(help_text='Unit of measure of the deleted item', max_length=10)),
                ('lot_number', models.CharField(db_index=True, help_text='Lot number that was orphaned', max_length=20, unique=True)),
                ('vendor_lot_number', models.CharField(blank=True, max_length=100, null=True)),
                ('quantity', models.FloatField(help_text='Total quantity in the lot')),
                ('quantity_remaining', models.FloatField(help_text='Quantity remaining in the lot')),
                ('received_date', models.DateTimeField(help_text='Original received date')),
                ('expiration_date', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(default='accepted', max_length=20)),
                ('po_number', models.CharField(blank=True, max_length=100, null=True)),
                ('freight_actual', models.FloatField(blank=True, null=True)),
                ('short_reason', models.CharField(blank=True, max_length=255, null=True)),
                ('reassigned_at', models.DateTimeField(blank=True, help_text='When this inventory was reassigned', null=True)),
                ('reassigned_by', models.CharField(blank=True, help_text='Who reassigned this inventory', max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When the item was deleted and inventory orphaned')),
                ('notes', models.TextField(blank=True, help_text='Additional notes about the orphaned inventory', null=True)),
                ('reassigned_item', models.ForeignKey(blank=True, help_text='Item this orphaned inventory was reassigned to', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reassigned_orphaned_inventory', to='erp_core.item')),
            ],
            options={
                'verbose_name_plural': 'Orphaned Inventory',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrphanedPurchaseOrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_item_sku', models.CharField(db_index=True, help_text='SKU of the deleted item', max_length=255)),
                ('original_item_name', models.CharField(help_text='Name of the deleted item', max_length=255)),
                ('original_item_vendor', models.CharField(blank=True, max_length=255, null=True)),
                ('original_item_unit', models.CharField(help_text='Unit of measure of the deleted item', max_length=10)),
                ('quantity_ordered', models.FloatField()),
                ('quantity_received', models.FloatField(default=0.0)),
                ('unit_price', models.FloatField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('reassigned_at', models.DateTimeField(blank=True, null=True)),
                ('reassigned_by', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When the item was deleted and PO item orphaned')),
                ('purchase_order', models.ForeignKey(help_text='Purchase order this item belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='orphaned_items', to='erp_core.purchaseorder')),
                ('reassigned_item', models.ForeignKey(blank=True, help_text='Item this orphaned PO item was reassigned to', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reassigned_orphaned_po_items', to='erp_core.item')),
            ],
            options={
                'verbose_name_plural': 'Orphaned Purchase Order Items',
                'ordering': ['-created_at'],
            },
        ),
    ]
