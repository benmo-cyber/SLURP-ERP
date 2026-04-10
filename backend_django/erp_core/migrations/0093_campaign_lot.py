# Manual migration: CampaignLot + ProductionBatch.campaign (ISO week YYWW + product code).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0092_productionbatch_batch_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='CampaignLot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anchor_date', models.DateField(help_text='Calendar date used to compute ISO week and YYWW prefix (Mon–Sun ISO week).')),
                ('product_code', models.CharField(max_length=40, help_text='Product code suffix, e.g. D1307 (pigment, solubility, form, strength).')),
                ('campaign_code', models.CharField(db_index=True, max_length=64, unique=True)),
                ('iso_year', models.PositiveSmallIntegerField()),
                ('iso_week', models.PositiveSmallIntegerField()),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaign_lots', to='erp_core.item')),
            ],
            options={
                'verbose_name': 'Campaign lot',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='productionbatch',
            name='campaign',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional campaign lot (YYWW+product). Batch lot remains primary for traceability.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='batches',
                to='erp_core.campaignlot',
            ),
        ),
    ]
