# Generated manually for ItemPreferredPackaging

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0141_item_coa_template_item"),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemPreferredPackaging",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "label",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional role label, e.g. Container, Liner, Other.",
                        max_length=64,
                    ),
                ),
                (
                    "suggest_qty",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "When True, Create Batch prefills suggested EA count from pack math "
                            "(full packs + one for partial)."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "finished_good",
                    models.ForeignKey(
                        limit_choices_to={"item_type__in": ["finished_good", "distributed_item"]},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preferred_packaging",
                        to="erp_core.item",
                    ),
                ),
                (
                    "packaging_item",
                    models.ForeignKey(
                        limit_choices_to={"item_type": "indirect_material"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="preferred_for_fps",
                        to="erp_core.item",
                    ),
                ),
            ],
            options={
                "verbose_name": "Preferred packaging",
                "verbose_name_plural": "Preferred packaging",
                "ordering": ["finished_good", "sort_order", "id"],
                "unique_together": {("finished_good", "packaging_item")},
            },
        ),
    ]
