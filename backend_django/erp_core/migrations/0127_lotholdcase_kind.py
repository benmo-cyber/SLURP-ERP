# Generated manually for LotHoldCase.kind

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0126_formulaitem_match_by_parent"),
    ]

    operations = [
        migrations.AddField(
            model_name="lotholdcase",
            name="kind",
            field=models.CharField(
                choices=[
                    ("receiving", "Receiving / investigation"),
                    ("awaiting_micro", "Awaiting micro / QC"),
                ],
                db_index=True,
                default="receiving",
                help_text="receiving = inbound issue; awaiting_micro = manufactured lot pending QC release.",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="lotholdcase",
            index=models.Index(
                fields=["kind", "status", "-opened_at"],
                name="erp_core_lo_kind_7c8a1e_idx",
            ),
        ),
    ]
