# Generated manually for ProductionBatch archive fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0127_lotholdcase_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionbatch",
            name="is_archived",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Archived closed batches are hidden from the production dash; searchable in Archive.",
            ),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
