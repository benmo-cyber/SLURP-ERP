# Unit for quantity + unit_price on a PO line (may differ from Item.unit_of_measure, e.g. order in kg).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0080_salesorder_actual_ship_date_if_missing'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorderitem',
            name='order_uom',
            field=models.CharField(
                blank=True,
                help_text='UoM for quantity_ordered and unit_price on this line (e.g. lbs, kg). Blank means use the item master UoM.',
                max_length=20,
                null=True,
            ),
        ),
    ]
