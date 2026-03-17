# Add quantity_on_hold for partial hold; backfill from status/on_hold

from django.db import migrations, models


def backfill_quantity_on_hold(apps, schema_editor):
    Lot = apps.get_model('erp_core', 'Lot')
    for lot in Lot.objects.filter(quantity_remaining__gt=0):
        if getattr(lot, 'status', None) == 'on_hold' or getattr(lot, 'on_hold', False):
            lot.quantity_on_hold = lot.quantity_remaining
            lot.save(update_fields=['quantity_on_hold'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0060_shipment_expected_ship_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='lot',
            name='quantity_on_hold',
            field=models.FloatField(default=0.0, help_text='Amount of this lot on hold (not available). Use for partial holds.'),
        ),
        migrations.RunPython(backfill_quantity_on_hold, noop_reverse),
    ]
