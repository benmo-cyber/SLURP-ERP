# Generated manually for VendorPricing model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0034_add_checkout_workflow_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorPricing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_name', models.CharField(db_index=True, max_length=255)),
                ('vendor_item_number', models.CharField(blank=True, max_length=255, null=True)),
                ('unit_price', models.FloatField()),
                ('unit_of_measure', models.CharField(choices=[('lbs', 'Pounds'), ('kg', 'Kilograms'), ('ea', 'Each')], default='lbs', max_length=10)),
                ('effective_date', models.DateField()),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_pricing', to='erp_core.item')),
            ],
            options={
                'ordering': ['vendor_name', 'item', '-effective_date'],
            },
        ),
        migrations.AddIndex(
            model_name='vendorpricing',
            index=models.Index(fields=['vendor_name', 'item', 'is_active'], name='erp_core_v_vendor__idx'),
        ),
        migrations.AlterUniqueTogether(
            name='vendorpricing',
            unique_together={('vendor_name', 'item', 'effective_date')},
        ),
    ]
