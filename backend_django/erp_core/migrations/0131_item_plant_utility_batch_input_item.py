from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0130_formula_multi_recipe"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="plant_utility",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Plant utility (e.g. DI water): appears on formulas and Cost Master, "
                    "but production skips lot picking and inventory deduction."
                ),
            ),
        ),
        migrations.AddField(
            model_name="productionbatchinput",
            name="item",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for plant-utility inputs; otherwise taken from lot.item.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="production_batch_inputs",
                to="erp_core.item",
            ),
        ),
        migrations.AlterField(
            model_name="productionbatchinput",
            name="lot",
            field=models.ForeignKey(
                blank=True,
                help_text="Null for plant-utility inputs (no inventory lot).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="production_batch_inputs",
                to="erp_core.lot",
            ),
        ),
    ]
