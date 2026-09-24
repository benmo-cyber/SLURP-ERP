# Generated manually for Item.coa_template_item

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0140_customer_coa_requirement"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="coa_template_item",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Item whose ItemCoaTestLine rows define this family's FPS COA. "
                    "Null = resolve by family default (master/parent pack)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="coa_template_dependents",
                to="erp_core.item",
            ),
        ),
    ]
