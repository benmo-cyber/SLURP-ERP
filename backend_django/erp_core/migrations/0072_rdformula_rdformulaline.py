# R&D Formulas: pre-commercialization BOM for cost estimation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0071_accountspayable_freight_tariff_shipment'),
    ]

    operations = [
        migrations.CreateModel(
            name='RDFormula',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Product name (e.g. Natural Red D1307)', max_length=255)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('approved', 'Approved'), ('scrapped', 'Scrapped')], default='draft', max_length=20)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
                'verbose_name': 'R&D Formula',
                'verbose_name_plural': 'R&D Formulas',
            },
        ),
        migrations.CreateModel(
            name='RDFormulaLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_type', models.CharField(choices=[('ingredient', 'Ingredient'), ('packaging', 'Packaging'), ('labor', 'Labor')], max_length=20)),
                ('sequence', models.PositiveSmallIntegerField(default=0, help_text='Order: R1=1, R2=2, P1=3, etc.')),
                ('description', models.CharField(blank=True, help_text='Display name when no item or override', max_length=255)),
                ('composition_pct', models.FloatField(blank=True, help_text='Composition % (ingredients/packaging); null for labor', null=True)),
                ('price_per_lb', models.FloatField(blank=True, help_text='Price per lb or per unit', null=True)),
                ('labor_flat_amount', models.FloatField(blank=True, help_text='Flat $ for labor line only', null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('item', models.ForeignKey(blank=True, help_text='Optional: link to Item for dropdown selection', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rd_formula_lines', to='erp_core.item')),
                ('rd_formula', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='erp_core.rdformula')),
            ],
            options={
                'ordering': ['rd_formula', 'line_type', 'sequence', 'id'],
                'unique_together': {('rd_formula', 'line_type', 'sequence')},
            },
        ),
    ]
