# Generated manually for LotHoldCase QC port from batch close

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0128_productionbatch_archive"),
    ]

    operations = [
        migrations.AddField(
            model_name="lotholdcase",
            name="qc_parameter_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="lotholdcase",
            name="qc_result_value",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lotholdcase",
            name="qc_initials",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
