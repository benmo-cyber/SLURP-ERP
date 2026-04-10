# Generated manually for COA customer copies (per sales allocation) and master quantity snapshot.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0102_item_coa_lot_certificate'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotcoacertificate',
            name='quantity_snapshot',
            field=models.FloatField(
                blank=True,
                help_text='Lot quantity (item UOM) shown on master COA PDF at issue time',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='lotcoacertificate',
            name='customer_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Deprecated: use customer-specific COAs on sales allocations.',
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name='lotcoacertificate',
            name='customer_po',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Deprecated: use customer-specific COAs on sales allocations.',
                max_length=120,
            ),
        ),
        migrations.CreateModel(
            name='LotCoaCustomerCopy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name', models.CharField(blank=True, default='', max_length=255)),
                ('customer_po', models.CharField(blank=True, default='', max_length=120)),
                (
                    'quantity_snapshot',
                    models.FloatField(help_text='Allocated quantity (item UOM) shown on this COA'),
                ),
                ('coa_pdf', models.FileField(blank=True, null=True, upload_to='coa_pdfs/customer/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'certificate',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='customer_copies',
                        to='erp_core.lotcoacertificate',
                    ),
                ),
                (
                    'sales_order_lot',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='coa_customer_copy',
                        to='erp_core.salesorderlot',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Lot COA (customer copy)',
                'verbose_name_plural': 'Lot COA customer copies',
                'ordering': ['-created_at'],
            },
        ),
    ]
