# Generated manually to add repack transaction types
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0044_recreate_lottransactionlog_state'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inventorytransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('receipt', 'Receipt'),
                    ('sale', 'Sale'),
                    ('adjustment', 'Adjustment'),
                    ('production', 'Production'),
                    ('production_input', 'Production Input'),
                    ('production_output', 'Production Output'),
                    ('repack_input', 'Repack Input'),
                    ('repack_output', 'Repack Output'),
                ],
                max_length=20
            ),
        ),
        migrations.AlterField(
            model_name='lottransactionlog',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('receipt', 'Receipt'),
                    ('production_input', 'Production Input'),
                    ('production_output', 'Production Output'),
                    ('repack_input', 'Repack Input'),
                    ('repack_output', 'Repack Output'),
                    ('sale', 'Sale'),
                    ('adjustment', 'Adjustment'),
                    ('allocation', 'Allocation'),
                    ('deallocation', 'Deallocation'),
                    ('manual', 'Manual'),
                    ('reversal', 'Reversal/Cancellation'),
                ],
                help_text='Type of transaction',
                max_length=20
            ),
        ),
    ]
