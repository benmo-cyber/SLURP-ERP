# Widen R&D family codes from 1 letter to 1–4 letters (e.g. HL-R001).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0112_pricing_whatif_line"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rdformulacodesequence",
            name="family_letter",
            field=models.CharField(
                help_text="Family code (1–4 letters), e.g. L or HL.",
                max_length=4,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="rdformula",
            name="family_letter",
            field=models.CharField(
                help_text=(
                    "Commercial family code (1–4 letters), e.g. L for Natural Blue, "
                    "HL for Natural Green. Used in R&D code."
                ),
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name="rdformula",
            name="rd_code",
            field=models.CharField(
                db_index=True,
                help_text=(
                    "Permanent R&D code (e.g. L-R001 or HL-R001). "
                    "Never reused, even if scrapped."
                ),
                max_length=20,
                unique=True,
            ),
        ),
    ]
