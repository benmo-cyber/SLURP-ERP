# Generated manually for SalesOrder.customer_po_pdf

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0050_vendor_payment_terms'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='customer_po_pdf',
            field=models.FileField(blank=True, help_text='Uploaded customer PO document (PDF)', null=True, upload_to='customer_pos/%Y/%m/'),
        ),
    ]
