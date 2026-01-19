# Generated migration to add missing Invoice columns

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0048_add_tariff_to_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='freight',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='invoice',
            name='tax',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='invoice',
            name='discount',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='invoice',
            name='grand_total',
            field=models.FloatField(default=0.0),
        ),
    ]
