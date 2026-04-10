# Add incoterms_place to CostMaster (e.g. "Long Beach, CA" for FCA Long Beach — pricing point; origin stays country of origin)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0069_customerpricing_incoterms_place'),
    ]

    operations = [
        migrations.AddField(
            model_name='costmaster',
            name='incoterms_place',
            field=models.CharField(blank=True, help_text='Named place for the Incoterm (e.g. "Long Beach, CA" for FCA Long Beach, CA). Origin remains country of origin.', max_length=255, null=True),
        ),
    ]
