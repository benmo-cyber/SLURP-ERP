# Multi-recipe per finished good + ProductionBatch.formula

import django.db.models.deletion
from django.db import migrations, models


def forwards_backfill(apps, schema_editor):
    Formula = apps.get_model("erp_core", "Formula")
    # Name existing rows; mark one default per FG.
    seen = set()
    for f in Formula.objects.order_by("finished_good_id", "id"):
        if not (f.name or "").strip():
            f.name = "Standard"
        if f.finished_good_id not in seen:
            f.is_default = True
            seen.add(f.finished_good_id)
        else:
            f.is_default = False
            # Ensure unique names if multiple somehow exist
            if Formula.objects.filter(
                finished_good_id=f.finished_good_id, name=f.name
            ).exclude(pk=f.pk).exists():
                f.name = f"{f.name} ({f.id})"
        f.save(update_fields=["name", "is_default"])


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0129_lotholdcase_qc_from_batch"),
    ]

    operations = [
        migrations.AddField(
            model_name="formula",
            name="name",
            field=models.CharField(
                default="Standard",
                help_text='Recipe name for this FG (e.g. "From G3403 3%%", "From G3405 5%%").',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="formula",
            name="is_default",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Default recipe used when no batch-specific recipe is set (QC release, shelf life).",
            ),
        ),
        migrations.AlterField(
            model_name="formula",
            name="finished_good",
            field=models.ForeignKey(
                limit_choices_to={"item_type": "finished_good"},
                on_delete=django.db.models.deletion.CASCADE,
                related_name="formulas",
                to="erp_core.item",
            ),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="formula",
            field=models.ForeignKey(
                blank=True,
                help_text="Recipe used for this batch (when FG has alternate make paths).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="batches",
                to="erp_core.formula",
            ),
        ),
        migrations.RunPython(forwards_backfill, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="formula",
            options={"ordering": ["-is_default", "name", "id"]},
        ),
        migrations.AddConstraint(
            model_name="formula",
            constraint=models.UniqueConstraint(
                fields=("finished_good", "name"),
                name="uniq_formula_fg_name",
            ),
        ),
    ]
