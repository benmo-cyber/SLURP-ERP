from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0146_campaign_coa"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionbatchinput",
            name="quantity_packs",
            field=models.FloatField(
                blank=True,
                help_text="Full-packs portion of quantity_used in item native UoM (from create-ticket packs field).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productionbatchinput",
            name="quantity_remnant",
            field=models.FloatField(
                blank=True,
                help_text="Remnant/partial portion of quantity_used in item native UoM (from create-ticket remnant field).",
                null=True,
            ),
        ),
    ]
