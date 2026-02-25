# Fix migration state: 0019 deleted Invoice/InvoiceItem but 0043 and 0049 alter them.
# This migration only updates the in-memory state so later migrations see the models.
# No database operations (tables may already exist from manual or alternate history).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0019_remove_account_parent_account_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Invoice',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('invoice_number', models.CharField(db_index=True, max_length=100, unique=True)),
                        ('invoice_type', models.CharField(choices=[('customer', 'Customer Invoice'), ('vendor', 'Vendor Bill')], max_length=20)),
                        ('customer_vendor_name', models.CharField(max_length=255)),
                        ('customer_vendor_id', models.CharField(blank=True, max_length=100, null=True)),
                        ('invoice_date', models.DateField()),
                        ('due_date', models.DateField(blank=True, null=True)),
                        ('status', models.CharField(choices=[('draft', 'Draft'), ('sent', 'Sent'), ('paid', 'Paid'), ('overdue', 'Overdue'), ('cancelled', 'Cancelled')], default='draft', max_length=20)),
                        ('subtotal', models.FloatField(default=0.0)),
                        ('tax_amount', models.FloatField(default=0.0)),
                        ('total_amount', models.FloatField(default=0.0)),
                        ('paid_amount', models.FloatField(default=0.0)),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'ordering': ['-invoice_date', '-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='InvoiceItem',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('description', models.CharField(max_length=255)),
                        ('quantity', models.FloatField()),
                        ('unit_price', models.FloatField()),
                        ('line_total', models.FloatField()),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='erp_core.invoice')),
                        ('item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoice_items', to='erp_core.item')),
                    ],
                    options={
                        'ordering': ['id'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
