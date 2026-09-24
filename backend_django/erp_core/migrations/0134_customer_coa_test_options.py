# Generated manually for customer COA display options

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0133_productionbatch_critical_control_point"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcoatestline",
            name="include_on_customer_coa",
            field=models.BooleanField(
                default=True,
                help_text="When True, this test is included by default on auto-generated customer COAs.",
            ),
        ),
        migrations.AddField(
            model_name="itemcoatestline",
            name="customer_result_display",
            field=models.CharField(
                choices=[
                    ("actual", "Show actual result"),
                    ("pass_fail", "Show Pass / Fail"),
                ],
                default="actual",
                help_text="Default Result column on customer COAs for this test.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="included_line_result_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="LotCoaLineResult pks to include. Empty until defaults applied or Customize saves.",
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="include_qc_row",
            field=models.BooleanField(
                default=True,
                help_text="Include formula QC row on the customer COA when the master has QC.",
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="result_display_mode",
            field=models.CharField(
                choices=[
                    ("actual", "All actual results"),
                    ("pass_fail", "All Pass / Fail"),
                    ("per_line", "Per-test (item defaults / overrides)"),
                ],
                default="per_line",
                help_text="How Result column values are shown on the customer PDF.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="line_display_overrides",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Map of line_result_id (str) → actual|pass_fail when mode is per_line.",
            ),
        ),
        migrations.AddField(
            model_name="lotcoacustomercopy",
            name="customization_saved",
            field=models.BooleanField(
                default=False,
                help_text="True after Quality Customize; empty included_line_result_ids then means include none.",
            ),
        ),
    ]
