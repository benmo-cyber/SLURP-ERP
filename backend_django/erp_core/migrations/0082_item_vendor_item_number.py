# Vendor catalog number (re-added — was on Item before migration 0019; stored on Item for PO/display).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0081_purchaseorderitem_order_uom'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='vendor_item_number',
            field=models.CharField(
                blank=True,
                help_text="Vendor's part / catalog number for this SKU (shown on POs next to vendor item name).",
                max_length=255,
                null=True,
            ),
        ),
    ]
