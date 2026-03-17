# Add carrier to SalesOrder for invoice SHIPPED VIA

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0055_shipment_dimensions_pieces'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='carrier',
            field=models.CharField(blank=True, help_text='Shipping carrier (e.g. FedEx, UPS); shown on invoice under SHIPPED VIA', max_length=255, null=True),
        ),
    ]
