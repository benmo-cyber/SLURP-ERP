from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0138_lotcoacertificate_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="lottransactionlog",
            name="po_number",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="PO number on the lot at transaction time (inbound pedigree)",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="lottransactionlog",
            name="vendor_lot_number",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Vendor lot number on the lot at transaction time",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="lottransactionlog",
            index=models.Index(
                fields=["po_number", "-logged_at"],
                name="erp_core_lo_po_numb_3c8a1d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="lottransactionlog",
            index=models.Index(
                fields=["vendor_lot_number", "-logged_at"],
                name="erp_core_lo_vendor__7b2e4f_idx",
            ),
        ),
    ]
