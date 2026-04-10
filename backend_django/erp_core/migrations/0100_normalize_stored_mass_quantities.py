# Data migration: snap float drift on batch-related quantities (e.g. 699.99 -> 700).
# See erp_core.mass_quantity.normalize_mass_quantity

from django.db import migrations


def _normalize_input_quantity_used(raw_qty, uom):
    """Match runtime: ea keeps 5 dp; mass uses normalize_mass_quantity."""
    from erp_core.mass_quantity import normalize_mass_quantity

    q = float(raw_qty)
    u = (uom or "").lower()
    if u == "ea":
        ri = round(q)
        if abs(q - ri) <= 0.01:
            return float(ri)
        return round(q, 5)
    return normalize_mass_quantity(q)


def forwards(apps, schema_editor):
    from erp_core.mass_quantity import normalize_mass_quantity

    ProductionBatch = apps.get_model("erp_core", "ProductionBatch")
    ProductionBatchInput = apps.get_model("erp_core", "ProductionBatchInput")
    ProductionBatchOutput = apps.get_model("erp_core", "ProductionBatchOutput")
    ProductionLog = apps.get_model("erp_core", "ProductionLog")

    batch_fields = (
        "quantity_produced",
        "quantity_actual",
        "variance",
        "wastes",
        "spills",
    )

    to_update_batches = []
    for b in ProductionBatch.objects.all().iterator(chunk_size=500):
        changed = False
        for field in batch_fields:
            val = getattr(b, field)
            if val is None:
                continue
            old = float(val)
            new_val = normalize_mass_quantity(old)
            if abs(new_val - old) > 1e-12:
                setattr(b, field, new_val)
                changed = True
        if changed:
            to_update_batches.append(b)
    if to_update_batches:
        ProductionBatch.objects.bulk_update(
            to_update_batches,
            list(batch_fields),
            batch_size=500,
        )

    to_update_outputs = []
    for o in ProductionBatchOutput.objects.all().iterator(chunk_size=500):
        old = float(o.quantity_produced)
        new_val = normalize_mass_quantity(old)
        if abs(new_val - old) > 1e-12:
            o.quantity_produced = new_val
            to_update_outputs.append(o)
    if to_update_outputs:
        ProductionBatchOutput.objects.bulk_update(
            to_update_outputs, ["quantity_produced"], batch_size=500
        )

    to_update_inputs = []
    for inp in ProductionBatchInput.objects.select_related("lot__item").iterator(chunk_size=500):
        uom = inp.lot.item.unit_of_measure if inp.lot and inp.lot.item_id else ""
        old = float(inp.quantity_used)
        new_val = _normalize_input_quantity_used(old, uom)
        if abs(new_val - old) > 1e-12:
            inp.quantity_used = new_val
            to_update_inputs.append(inp)
    if to_update_inputs:
        ProductionBatchInput.objects.bulk_update(
            to_update_inputs, ["quantity_used"], batch_size=500
        )

    log_fields = (
        "quantity_produced",
        "quantity_actual",
        "variance",
        "wastes",
        "spills",
        "output_quantity",
    )
    to_update_logs = []
    for log in ProductionLog.objects.all().iterator(chunk_size=500):
        changed = False
        for field in log_fields:
            val = getattr(log, field, None)
            if val is None:
                continue
            old = float(val)
            new_val = normalize_mass_quantity(old)
            if abs(new_val - old) > 1e-12:
                setattr(log, field, new_val)
                changed = True
        if changed:
            to_update_logs.append(log)
    if to_update_logs:
        ProductionLog.objects.bulk_update(
            to_update_logs, list(log_fields), batch_size=500
        )


def backwards(apps, schema_editor):
    # Cannot restore pre-normalization floats
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0099_item_sku_family_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
