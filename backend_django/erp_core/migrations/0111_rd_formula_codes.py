# Permanent R&D codes: family letter + L-R001 style sequence; commercialize link fields.

from django.db import migrations, models


def backfill_rd_codes(apps, schema_editor):
    RDFormula = apps.get_model("erp_core", "RDFormula")
    RDFormulaCodeSequence = apps.get_model("erp_core", "RDFormulaCodeSequence")

    max_by_letter = {}
    for i, rd in enumerate(RDFormula.objects.order_by("id"), start=1):
        letter = (getattr(rd, "family_letter", None) or "U").strip().upper()[:1] or "U"
        if not letter.isalpha():
            letter = "U"
        n = max_by_letter.get(letter, 0) + 1
        max_by_letter[letter] = n
        code = f"{letter}-R{n:03d}"
        rd.family_letter = letter
        rd.rd_code = code
        rd.save(update_fields=["family_letter", "rd_code"])

    for letter, n in max_by_letter.items():
        RDFormulaCodeSequence.objects.update_or_create(
            family_letter=letter,
            defaults={"sequence_number": n},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0110_customer_quotes"),
    ]

    operations = [
        migrations.CreateModel(
            name="RDFormulaCodeSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("family_letter", models.CharField(max_length=1, unique=True)),
                ("sequence_number", models.IntegerField(default=0)),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "R&D formula code sequence",
                "verbose_name_plural": "R&D formula code sequences",
                "ordering": ["family_letter"],
            },
        ),
        migrations.AddField(
            model_name="rdformula",
            name="commercial_sku",
            field=models.CharField(
                blank=True,
                help_text="Commercial SKU after graduation (e.g. L1303). R&D code stays for history.",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="rdformula",
            name="family_letter",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Commercial family letter only (e.g. L for Natural Blue). Assigned at create; used in R&D code.",
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name="rdformula",
            name="rd_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Permanent R&D code (e.g. L-R001). Never reused, even if scrapped.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="rdformula",
            name="name",
            field=models.CharField(help_text="Product name (e.g. Natural Red trial)", max_length=255),
        ),
        migrations.AlterField(
            model_name="rdformula",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("approved", "Approved"),
                    ("scrapped", "Scrapped"),
                    ("commercialized", "Commercialized"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_rd_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="rdformula",
            name="family_letter",
            field=models.CharField(
                help_text="Commercial family letter only (e.g. L for Natural Blue). Assigned at create; used in R&D code.",
                max_length=1,
            ),
        ),
        migrations.AlterField(
            model_name="rdformula",
            name="rd_code",
            field=models.CharField(
                db_index=True,
                help_text="Permanent R&D code (e.g. L-R001). Never reused, even if scrapped.",
                max_length=20,
                unique=True,
            ),
        ),
    ]
