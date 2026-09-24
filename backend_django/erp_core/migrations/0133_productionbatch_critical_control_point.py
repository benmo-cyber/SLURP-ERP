# Generated manually for ProductionBatch.critical_control_point

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0132_accountspayable_invoice_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionbatch",
            name="critical_control_point",
            field=models.ForeignKey(
                blank=True,
                help_text="CCP for pack-change repack tickets (screen check). Relabel / production use formula CCP when set.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="batches",
                to="erp_core.criticalcontrolpoint",
            ),
        ),
    ]
