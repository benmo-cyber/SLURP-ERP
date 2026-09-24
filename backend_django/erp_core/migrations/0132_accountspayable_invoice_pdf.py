from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0131_item_plant_utility_batch_input_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountspayable",
            name="invoice_pdf",
            field=models.FileField(
                blank=True,
                help_text="Uploaded vendor invoice PDF for this payable",
                null=True,
                upload_to="ap_invoices/",
            ),
        ),
        migrations.AddField(
            model_name="accountspayable",
            name="invoice_pdf_uploaded_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the vendor invoice PDF was last uploaded",
                null=True,
            ),
        ),
    ]
