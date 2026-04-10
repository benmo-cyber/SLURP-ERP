from django.db import migrations, models


class Migration(migrations.Migration):
    """ProductionBatch.batch_type was in models but never had a migration; SQLite lacked the column."""

    dependencies = [
        ('erp_core', '0091_productionbatch_batch_ticket_mass_unit'),
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
    ]
