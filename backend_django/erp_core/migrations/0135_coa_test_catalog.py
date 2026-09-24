# Generated manually for CoaTestCatalog + ItemCoaTestLine catalog link / typical_result

from django.db import migrations, models
import django.db.models.deletion


SEED = [
    {
        "sort_order": 10,
        "test_name": "Aerobic Plate Count",
        "specification_text": "≤ 10,000 CFU/g",
        "result_kind": "text_only",
        "typical_result": "≤ 10,000 CFU/g",
        "customer_result_display": "actual",
    },
    {
        "sort_order": 20,
        "test_name": "Yeast & Mold",
        "specification_text": "≤ 1,000 CFU/g",
        "result_kind": "text_only",
        "typical_result": "≤ 1,000 CFU/g",
        "customer_result_display": "actual",
    },
    {
        "sort_order": 30,
        "test_name": "Coliforms",
        "specification_text": "≤ 100 CFU/g",
        "result_kind": "text_only",
        "typical_result": "≤ 100 CFU/g",
        "customer_result_display": "actual",
    },
    {
        "sort_order": 40,
        "test_name": "E. coli",
        "specification_text": "Negative / < 10 CFU/g",
        "result_kind": "pass_fail",
        "typical_result": "Negative",
        "customer_result_display": "pass_fail",
    },
    {
        "sort_order": 50,
        "test_name": "Salmonella",
        "specification_text": "Negative / 25 g",
        "result_kind": "pass_fail",
        "typical_result": "Negative",
        "customer_result_display": "pass_fail",
    },
    {
        "sort_order": 60,
        "test_name": "Listeria monocytogenes",
        "specification_text": "Negative / 25 g",
        "result_kind": "pass_fail",
        "typical_result": "Negative",
        "customer_result_display": "pass_fail",
    },
]


def seed_catalog(apps, schema_editor):
    CoaTestCatalog = apps.get_model("erp_core", "CoaTestCatalog")
    for row in SEED:
        CoaTestCatalog.objects.update_or_create(
            test_name=row["test_name"],
            defaults={
                "sort_order": row["sort_order"],
                "specification_text": row["specification_text"],
                "result_kind": row["result_kind"],
                "typical_result": row["typical_result"],
                "include_on_customer_coa": True,
                "customer_result_display": row["customer_result_display"],
                "is_active": True,
            },
        )


def unseed_catalog(apps, schema_editor):
    CoaTestCatalog = apps.get_model("erp_core", "CoaTestCatalog")
    CoaTestCatalog.objects.filter(test_name__in=[r["test_name"] for r in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0134_customer_coa_test_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoaTestCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("test_name", models.CharField(max_length=255, unique=True)),
                (
                    "specification_text",
                    models.TextField(
                        help_text="Typical COA Specification text (autofilled onto product lines)"
                    ),
                ),
                (
                    "result_kind",
                    models.CharField(
                        choices=[
                            ("numeric_range", "Numeric range (min–max)"),
                            ("numeric_minimum", "Numeric minimum (e.g. NLT)"),
                            ("pass_fail", "Pass / fail (text)"),
                            ("text_only", "Text only (no auto pass/fail)"),
                        ],
                        default="text_only",
                        max_length=32,
                    ),
                ),
                ("numeric_min", models.FloatField(blank=True, null=True)),
                ("numeric_max", models.FloatField(blank=True, null=True)),
                (
                    "typical_result",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Typical result text prefilled when recording micro/COA at hold release",
                        max_length=500,
                    ),
                ),
                ("include_on_customer_coa", models.BooleanField(default=True)),
                (
                    "customer_result_display",
                    models.CharField(
                        choices=[
                            ("actual", "Show actual result"),
                            ("pass_fail", "Show Pass / Fail"),
                        ],
                        default="actual",
                        max_length=16,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "COA test catalog",
                "verbose_name_plural": "COA test catalog",
                "ordering": ["sort_order", "test_name", "id"],
            },
        ),
        migrations.AddField(
            model_name="itemcoatestline",
            name="catalog_test",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional link to the global catalog entry this line was created from",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="item_lines",
                to="erp_core.coatestcatalog",
            ),
        ),
        migrations.AddField(
            model_name="itemcoatestline",
            name="typical_result",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Prefills the result field on awaiting-micro release",
                max_length=500,
            ),
        ),
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
