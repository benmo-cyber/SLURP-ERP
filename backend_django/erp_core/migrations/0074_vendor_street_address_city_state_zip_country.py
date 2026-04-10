# Add Vendor address fields (street_address, city, state, zip_code, country)
# so DB matches the model and /api/vendors/ can serialize without OperationalError.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0073_service_vendor_contacts_notify_party'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
            name='street_address',
            field=models.CharField(blank=True, help_text='Street address', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='vendor',
            name='city',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='vendor',
            name='state',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='vendor',
            name='zip_code',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='vendor',
            name='country',
            field=models.CharField(blank=True, default='USA', max_length=100, null=True),
        ),
    ]
