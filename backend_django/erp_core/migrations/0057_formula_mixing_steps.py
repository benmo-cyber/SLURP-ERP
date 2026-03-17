# Add mixing steps 1-6 to Formula for batch instructions

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0056_salesorder_carrier'),
    ]

    operations = [
        migrations.AddField(
            model_name='formula',
            name='mixing_step_1',
            field=models.TextField(blank=True, help_text='Mixing step 1', null=True),
        ),
        migrations.AddField(
            model_name='formula',
            name='mixing_step_2',
            field=models.TextField(blank=True, help_text='Mixing step 2', null=True),
        ),
        migrations.AddField(
            model_name='formula',
            name='mixing_step_3',
            field=models.TextField(blank=True, help_text='Mixing step 3', null=True),
        ),
        migrations.AddField(
            model_name='formula',
            name='mixing_step_4',
            field=models.TextField(blank=True, help_text='Mixing step 4', null=True),
        ),
        migrations.AddField(
            model_name='formula',
            name='mixing_step_5',
            field=models.TextField(blank=True, help_text='Mixing step 5', null=True),
        ),
        migrations.AddField(
            model_name='formula',
            name='mixing_step_6',
            field=models.TextField(blank=True, help_text='Mixing step 6', null=True),
        ),
    ]
