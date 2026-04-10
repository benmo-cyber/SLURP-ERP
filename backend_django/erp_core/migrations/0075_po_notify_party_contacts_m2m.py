# Replace single notify_party_contact (FK) with multiple notify_party_contacts (M2M)

from django.db import migrations, models


def copy_notify_party_to_m2m(apps, schema_editor):
    PurchaseOrder = apps.get_model('erp_core', 'PurchaseOrder')
    for po in PurchaseOrder.objects.exclude(notify_party_contact=None):
        po.notify_party_contacts.add(po.notify_party_contact)


def noop_reverse(apps, schema_editor):
    pass  # Not restoring old FK from M2M to keep migration simple


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0074_vendor_street_address_city_state_zip_country'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='notify_party_contacts',
            field=models.ManyToManyField(
                blank=True,
                help_text='Notify party contacts (e.g. customs broker by port) for importation',
                related_name='purchase_orders_as_notify_party',
                to='erp_core.vendorcontact',
            ),
        ),
        migrations.RunPython(copy_notify_party_to_m2m, noop_reverse),
        migrations.RemoveField(
            model_name='purchaseorder',
            name='notify_party_contact',
        ),
    ]
