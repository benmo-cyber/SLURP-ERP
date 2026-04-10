from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0106_formula_shelf_life_months'),
    ]

    operations = [
        migrations.AddField(
            model_name='lot',
            name='manufacture_date',
            field=models.DateTimeField(
                blank=True,
                help_text='Manufacturer production or pack date when known (common for distributed / resale goods).',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='checkinlog',
            name='manufacture_date',
            field=models.DateTimeField(
                blank=True,
                help_text='Manufacturer date when recorded at check-in (snapshot)',
                null=True,
            ),
        ),
    ]
