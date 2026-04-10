# Snap stored batch input line quantities that are within 0.05 of a whole number (mass/ea).
# Complements 0100 (0.01); fixes rows like 1049.96 so SUM matches intent after conversions.

from django.db import migrations


def forwards(apps, schema_editor):
    from erp_core.mass_quantity import snap_stored_batch_input_quantity

    ProductionBatchInput = apps.get_model("erp_core", "ProductionBatchInput")
    to_update = []
    for inp in ProductionBatchInput.objects.select_related("lot__item").iterator(chunk_size=500):
        lot = inp.lot
        uom = lot.item.unit_of_measure if lot and lot.item_id else "lbs"
        old = float(inp.quantity_used)
        new = snap_stored_batch_input_quantity(old, uom)
        if abs(new - old) > 1e-12:
            inp.quantity_used = new
            to_update.append(inp)
    if to_update:
        ProductionBatchInput.objects.bulk_update(to_update, ["quantity_used"], batch_size=500)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0100_normalize_stored_mass_quantities"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
