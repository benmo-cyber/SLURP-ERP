# Generated manually for LotShelfLifeExtension

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0142_item_preferred_packaging"),
    ]

    operations = [
        migrations.CreateModel(
            name="LotShelfLifeExtension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qc_date", models.DateField(help_text="Date QC was run for this extension")),
                (
                    "extension_months",
                    models.PositiveSmallIntegerField(
                        help_text="Shelf life extension length in months from qc_date"
                    ),
                ),
                ("previous_expiration", models.DateTimeField(blank=True, null=True)),
                ("new_expiration", models.DateTimeField()),
                ("qc_parameter_name", models.CharField(blank=True, default="", max_length=255)),
                ("qc_spec_min", models.FloatField(blank=True, null=True)),
                ("qc_spec_max", models.FloatField(blank=True, null=True)),
                (
                    "qc_result_value",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Optional new color/QC result from re-test",
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("recorded_by", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "certificate",
                    models.ForeignKey(
                        blank=True,
                        help_text="Master COA refreshed (or created) for this extension",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shelf_life_extensions",
                        to="erp_core.lotcoacertificate",
                    ),
                ),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shelf_life_extensions",
                        to="erp_core.lot",
                    ),
                ),
            ],
            options={
                "verbose_name": "Lot shelf life extension",
                "verbose_name_plural": "Lot shelf life extensions",
                "ordering": ["-created_at"],
            },
        ),
    ]
