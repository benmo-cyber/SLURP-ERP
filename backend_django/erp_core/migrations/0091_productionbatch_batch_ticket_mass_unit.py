from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0090_salesorder_actual_ship_date_if_missing_again'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionbatch',
            name='batch_ticket_mass_unit',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Default mass unit for batch ticket PDF pick list and batch totals. Empty=native (each line's item UoM). 'lbs' or 'kg' converts all mass quantities.",
                max_length=16,
            ),
        ),
    ]
