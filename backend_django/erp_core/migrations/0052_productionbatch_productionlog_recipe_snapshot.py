# Recipe snapshot for audit: batch % overrides and substitutions

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0051_salesorder_customer_po_pdf'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionbatch',
            name='recipe_snapshot',
            field=models.TextField(blank=True, help_text='JSON: formula overrides used (batch %, substitutions) for audit', null=True),
        ),
        migrations.AddField(
            model_name='productionlog',
            name='recipe_snapshot',
            field=models.TextField(blank=True, help_text='JSON: batch recipe overrides (%, substitutions) at time of closure', null=True),
        ),
    ]
