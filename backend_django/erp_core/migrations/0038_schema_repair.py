"""Add columns present in models but missing from drifted SQLite schema."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0037_batchnumbersequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionbatch',
            name='batch_type',
            field=models.CharField(
                choices=[('production', 'Production'), ('repack', 'Repack')],
                default='production',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='salesorder',
            name='actual_ship_date',
            field=models.DateTimeField(
                blank=True,
                help_text='Actual ship date',
                null=True,
            ),
        ),
    ]
