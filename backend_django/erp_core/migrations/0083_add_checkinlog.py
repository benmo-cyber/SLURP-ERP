# CheckInLog model existed in code without a migration; creates erp_core_checkinlog for new DBs.
# If your database already has this table from a manual script, run:
#   python manage.py migrate erp_core 0083 --fake

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0082_item_vendor_item_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='CheckInLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lot_number', models.CharField(db_index=True, help_text='Lot number at time of check-in', max_length=100)),
                ('item_id', models.IntegerField(blank=True, null=True)),
                ('item_sku', models.CharField(db_index=True, max_length=255)),
                ('item_name', models.CharField(max_length=255)),
                (
                    'item_type',
                    models.CharField(
                        choices=[
                            ('raw_material', 'Raw Material'),
                            ('distributed_item', 'Distributed Item'),
                            ('finished_good', 'Finished Good'),
                            ('indirect_material', 'Indirect Material'),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    'item_unit_of_measure',
                    models.CharField(
                        choices=[('lbs', 'Pounds'), ('kg', 'Kilograms'), ('ea', 'Each')],
                        max_length=10,
                    ),
                ),
                ('po_number', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('vendor_name', models.CharField(blank=True, max_length=255, null=True)),
                ('received_date', models.DateTimeField(help_text='Date material was received')),
                ('vendor_lot_number', models.CharField(blank=True, max_length=100, null=True)),
                ('quantity', models.FloatField(help_text='Quantity received in item native unit')),
                (
                    'quantity_unit',
                    models.CharField(
                        choices=[('lbs', 'Pounds'), ('kg', 'Kilograms'), ('ea', 'Each')],
                        default='lbs',
                        help_text='Unit of measure for quantity',
                        max_length=10,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('accepted', 'Accepted'),
                            ('rejected', 'Rejected'),
                            ('on_hold', 'On Hold'),
                        ],
                        default='accepted',
                        max_length=20,
                    ),
                ),
                ('short_reason', models.TextField(blank=True, help_text='Reason for short quantity if applicable', null=True)),
                ('coa', models.BooleanField(default=False, help_text='Certificate of Analysis received')),
                ('prod_free_pests', models.BooleanField(default=False, help_text='Product free of pests')),
                ('carrier_free_pests', models.BooleanField(default=False, help_text='Carrier free of pests')),
                ('shipment_accepted', models.BooleanField(default=False, help_text='Shipment accepted')),
                ('initials', models.CharField(blank=True, help_text='Initials of person who checked in', max_length=50, null=True)),
                ('carrier', models.CharField(blank=True, max_length=255, null=True)),
                ('freight_actual', models.FloatField(blank=True, help_text='Actual freight cost', null=True)),
                ('notes', models.TextField(blank=True, help_text='Additional notes from check-in', null=True)),
                ('checked_in_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('checked_in_by', models.CharField(blank=True, help_text='User who performed check-in', max_length=255, null=True)),
                (
                    'lot',
                    models.ForeignKey(
                        blank=True,
                        help_text='Related lot (null if lot was deleted)',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='check_in_logs',
                        to='erp_core.lot',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Check-In Log',
                'verbose_name_plural': 'Check-In Logs',
                'ordering': ['-checked_in_at'],
            },
        ),
        migrations.AddIndex(
            model_name='checkinlog',
            index=models.Index(fields=['-checked_in_at'], name='erp_core_ch_checked_135396_idx'),
        ),
        migrations.AddIndex(
            model_name='checkinlog',
            index=models.Index(fields=['item_sku', '-checked_in_at'], name='erp_core_ch_item_sk_b89b29_idx'),
        ),
        migrations.AddIndex(
            model_name='checkinlog',
            index=models.Index(fields=['po_number', '-checked_in_at'], name='erp_core_ch_po_numb_4f8c42_idx'),
        ),
        migrations.AddIndex(
            model_name='checkinlog',
            index=models.Index(fields=['lot_number', '-checked_in_at'], name='erp_core_ch_lot_num_207f1c_idx'),
        ),
    ]
