# Named R&D product families (Natural Green / HL, etc.); backfill from existing codes.

from django.db import migrations, models


def backfill_families(apps, schema_editor):
    RDFormula = apps.get_model("erp_core", "RDFormula")
    RDFormulaCodeSequence = apps.get_model("erp_core", "RDFormulaCodeSequence")
    RDFormulaFamily = apps.get_model("erp_core", "RDFormulaFamily")

    codes = set()
    for code in RDFormula.objects.exclude(family_letter="").values_list("family_letter", flat=True):
        c = (code or "").strip().upper()
        if c:
            codes.add(c)
    for code in RDFormulaCodeSequence.objects.values_list("family_letter", flat=True):
        c = (code or "").strip().upper()
        if c:
            codes.add(c)

    # Sensible starter names for common examples; others get a rename-friendly placeholder.
    known = {
        "L": "Natural Blue",
        "HL": "Natural Green",
    }
    for code in sorted(codes):
        RDFormulaFamily.objects.get_or_create(
            code=code,
            defaults={"name": known.get(code, f"Family {code}"), "is_active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0113_rd_family_code_maxlen"),
    ]

    operations = [
        migrations.CreateModel(
            name="RDFormulaFamily",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "code",
                    models.CharField(
                        help_text="1–4 letter family code used in R&D / commercial SKUs (e.g. L, HL).",
                        max_length=4,
                        unique=True,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Product line name shown in UI (e.g. Natural Green, Natural Blue).",
                        max_length=120,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "R&D formula family",
                "verbose_name_plural": "R&D formula families",
                "ordering": ["name", "code"],
            },
        ),
        migrations.RunPython(backfill_families, migrations.RunPython.noop),
    ]
