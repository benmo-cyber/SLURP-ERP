# Add payment_terms to Vendor for AP due date calculation (Quality > Vendor approval)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0049_add_invoice_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendor',
            name='payment_terms',
            field=models.CharField(blank=True, help_text='Payment terms (e.g., "Net 30", "Net 60", "Due on Receipt")', max_length=50, null=True),
        ),
    ]
