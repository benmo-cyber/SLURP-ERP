from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0137_shipment_fulfillment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotcoacertificate',
            name='source',
            field=models.CharField(
                choices=[('in_house', 'In-house micro / QC'), ('supplier', 'Supplier COA')],
                db_index=True,
                default='in_house',
                help_text='in_house = hold release; supplier = check-in / relabel clone from inbound.',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='lotcoacertificate',
            name='source_lot',
            field=models.ForeignKey(
                blank=True,
                help_text='When set, this cert was cloned from another lot (e.g. relabel output).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='coa_certificates_cloned_from',
                to='erp_core.lot',
            ),
        ),
    ]
