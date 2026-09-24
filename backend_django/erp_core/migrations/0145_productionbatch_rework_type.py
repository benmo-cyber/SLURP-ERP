# Alter ProductionBatch.batch_type choices to include rework

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0144_customer_rma"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productionbatch",
            name="batch_type",
            field=models.CharField(
                choices=[
                    ("production", "Production"),
                    ("repack", "Repack"),
                    ("rework", "Rework"),
                ],
                default="production",
                max_length=20,
            ),
        ),
    ]
