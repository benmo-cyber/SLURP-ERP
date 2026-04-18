# Backfill erp_core_customer.bill_to_* from headquarters when bill-to is empty or incomplete.

from django.db import migrations


def _nz(v):
    return (v or '').strip() if v is not None else ''


def forwards(apps, schema_editor):
    Customer = apps.get_model('erp_core', 'Customer')
    for c in Customer.objects.iterator():
        bt_addr = _nz(getattr(c, 'bill_to_address', None))
        bt_city = _nz(getattr(c, 'bill_to_city', None))
        bt_state = _nz(getattr(c, 'bill_to_state', None))
        bt_zip = _nz(getattr(c, 'bill_to_zip_code', None))
        bt_co = _nz(getattr(c, 'bill_to_country', None))
        any_bt = bool(bt_addr or bt_city or bt_state or bt_zip or bt_co)

        hq_addr = _nz(getattr(c, 'address', None))
        hq_city = _nz(getattr(c, 'city', None))
        hq_state = _nz(getattr(c, 'state', None))
        hq_zip = _nz(getattr(c, 'zip_code', None))
        hq_co = _nz(getattr(c, 'country', None))
        any_hq = bool(hq_addr or hq_city or hq_state or hq_zip)

        if not any_bt and any_hq:
            c.bill_to_address = getattr(c, 'address', None)
            c.bill_to_city = getattr(c, 'city', None)
            c.bill_to_state = getattr(c, 'state', None)
            c.bill_to_zip_code = getattr(c, 'zip_code', None)
            c.bill_to_country = getattr(c, 'country', None)
            c.save(
                update_fields=[
                    'bill_to_address',
                    'bill_to_city',
                    'bill_to_state',
                    'bill_to_zip_code',
                    'bill_to_country',
                ]
            )
        elif any_bt:
            updates = {}
            if not bt_addr and hq_addr:
                updates['bill_to_address'] = c.address
            if not bt_city and hq_city:
                updates['bill_to_city'] = c.city
            if not bt_state and hq_state:
                updates['bill_to_state'] = c.state
            if not bt_zip and hq_zip:
                updates['bill_to_zip_code'] = c.zip_code
            if not bt_co and hq_co:
                updates['bill_to_country'] = c.country
            if updates:
                for k, v in updates.items():
                    setattr(c, k, v)
                c.save(update_fields=list(updates.keys()))


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0107_lot_manufacture_date'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
