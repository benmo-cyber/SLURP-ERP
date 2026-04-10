# Service vendors (e.g. customs broker), vendor contacts, and PO notify party

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0072_rdformula_rdformulaline'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
            name='is_service_vendor',
            field=models.BooleanField(default=False, help_text='Service vendor (e.g. customs broker) with contacts for notify party'),
        ),
        migrations.AddField(
            model_name='vendor',
            name='service_vendor_type',
            field=models.CharField(blank=True, choices=[('', '—'), ('customs_broker', 'Customs Broker')], help_text='Type of service vendor', max_length=50, null=True),
        ),
        migrations.CreateModel(
            name='VendorContact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Contact or office name', max_length=255)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone', models.CharField(blank=True, max_length=50, null=True)),
                ('location_label', models.CharField(blank=True, help_text='Port or location (e.g. Long Beach, Houston)', max_length=100, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='erp_core.vendor')),
            ],
            options={
                'ordering': ['vendor', 'location_label', 'name'],
                'verbose_name': 'Vendor contact',
                'verbose_name_plural': 'Vendor contacts',
            },
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='notify_party_contact',
            field=models.ForeignKey(blank=True, help_text='Notify party (e.g. customs broker contact) for importation', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders', to='erp_core.vendorcontact'),
        ),
    ]
