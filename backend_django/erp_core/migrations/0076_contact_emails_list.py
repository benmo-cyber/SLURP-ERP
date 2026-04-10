# Replace single email with emails JSON list on VendorContact and CustomerContact

from django.db import migrations, models


def copy_vendor_email_to_emails(apps, schema_editor):
    VendorContact = apps.get_model('erp_core', 'VendorContact')
    for vc in VendorContact.objects.all():
        em = []
        e = getattr(vc, 'email', None)
        if e:
            em = [str(e).strip()]
        vc.emails = em
        vc.save(update_fields=['emails'])


def copy_customer_email_to_emails(apps, schema_editor):
    CustomerContact = apps.get_model('erp_core', 'CustomerContact')
    for cc in CustomerContact.objects.all():
        em = []
        e = getattr(cc, 'email', None)
        if e:
            em = [str(e).strip()]
        cc.emails = em
        cc.save(update_fields=['emails'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0075_po_notify_party_contacts_m2m'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorcontact',
            name='emails',
            field=models.JSONField(blank=True, default=list, help_text='Email addresses (list of strings; multiple allowed)'),
        ),
        migrations.AddField(
            model_name='customercontact',
            name='emails',
            field=models.JSONField(blank=True, default=list, help_text='Email addresses (list of strings; multiple allowed)'),
        ),
        migrations.RunPython(copy_vendor_email_to_emails, noop_reverse),
        migrations.RunPython(copy_customer_email_to_emails, noop_reverse),
        migrations.RemoveField(model_name='vendorcontact', name='email'),
        migrations.RemoveField(model_name='customercontact', name='email'),
    ]
