# Bank reconciliation for GL vs bank statement

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0052_productionbatch_productionlog_recipe_snapshot'),
    ]

    operations = [
        migrations.CreateModel(
            name='BankReconciliation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('statement_date', models.DateField(help_text='Bank statement date')),
                ('statement_balance', models.FloatField(help_text='Ending balance per bank statement')),
                ('reconciled_at', models.DateTimeField(blank=True, help_text='When reconciliation was completed', null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(on_delete=models.CASCADE, related_name='bank_reconciliations', to='erp_core.account')),
            ],
            options={
                'ordering': ['-statement_date'],
                'verbose_name_plural': 'Bank Reconciliations',
            },
        ),
        migrations.AddIndex(
            model_name='bankreconciliation',
            index=models.Index(fields=['account', 'statement_date'], name='erp_core_ba_account_8a0b0d_idx'),
        ),
    ]
