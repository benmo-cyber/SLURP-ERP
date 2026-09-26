# Campaign COA certificates + immutable customer copies (basis / is_current).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0145_productionbatch_rework_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignCoaCertificate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField(default=1)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("manufacture_date", models.DateField(help_text="First calendar day any campaign batch was closed.")),
                ("expiration_date", models.DateTimeField(help_text="manufacture_date + FPS / formula shelf_life_months.")),
                ("quantity_snapshot", models.FloatField(blank=True, help_text="Sum of member net yields (item UOM) at issue.", null=True)),
                ("qc_parameter_name_snapshot", models.CharField(blank=True, default="", max_length=255)),
                ("qc_spec_min_snapshot", models.FloatField(blank=True, null=True)),
                ("qc_spec_max_snapshot", models.FloatField(blank=True, null=True)),
                ("qc_result_value", models.FloatField(blank=True, help_text="Net-yield-weighted mean of member lot QC results.", null=True)),
                ("qc_result_pass", models.BooleanField(blank=True, null=True)),
                ("coa_pdf", models.FileField(blank=True, null=True, upload_to="coa_pdfs/campaign/")),
                ("recorded_by", models.CharField(blank=True, default="", help_text="Initials / username on first issue.", max_length=255)),
                ("issued_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="coa_certificates", to="erp_core.campaignlot")),
            ],
            options={
                "verbose_name": "Campaign COA certificate",
                "verbose_name_plural": "Campaign COA certificates",
                "ordering": ["-issued_at"],
            },
        ),
        migrations.CreateModel(
            name="CampaignCoaLineResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("test_name", models.CharField(max_length=255)),
                ("specification_text", models.TextField()),
                ("result_text", models.CharField(max_length=500)),
                ("passes", models.BooleanField(blank=True, null=True)),
                ("certificate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="line_results", to="erp_core.campaigncoacertificate")),
                ("item_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="campaign_coa_results", to="erp_core.itemcoatestline")),
            ],
            options={
                "verbose_name": "Campaign COA line result",
                "verbose_name_plural": "Campaign COA line results",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="CampaignShelfLifeExtension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qc_date", models.DateField()),
                ("extension_months", models.PositiveSmallIntegerField()),
                ("previous_expiration", models.DateTimeField(blank=True, null=True)),
                ("new_expiration", models.DateTimeField()),
                ("qc_parameter_name", models.CharField(blank=True, default="", max_length=255)),
                ("qc_spec_min", models.FloatField(blank=True, null=True)),
                ("qc_spec_max", models.FloatField(blank=True, null=True)),
                ("qc_result_value", models.FloatField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("recorded_by", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shelf_life_extensions", to="erp_core.campaignlot")),
                ("certificate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shelf_life_extensions", to="erp_core.campaigncoacertificate")),
            ],
            options={
                "verbose_name": "Campaign shelf life extension",
                "verbose_name_plural": "Campaign shelf life extensions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="coa_basis",
            field=models.CharField(
                choices=[("batch", "Batch lot COA"), ("campaign", "Campaign COA")],
                default="batch",
                help_text="batch = this lot master; campaign = campaign composite (when available).",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="is_current",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="Current customer PDF for this allocation. Prior issued copies stay for history.",
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="campaign_certificate",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="customer_copies",
                to="erp_core.campaigncoacertificate",
            ),
        ),
        migrations.AlterField(
            model_name="lotcoacustomercopy",
            name="sales_order_lot",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="coa_customer_copies",
                to="erp_core.salesorderlot",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaigncoacertificate",
            constraint=models.UniqueConstraint(fields=("campaign", "version"), name="uniq_campaign_coa_version"),
        ),
        migrations.AddConstraint(
            model_name="lotcoacustomercopy",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_current=True),
                fields=("sales_order_lot",),
                name="uniq_current_customer_coa_per_sol",
            ),
        ),
    ]
