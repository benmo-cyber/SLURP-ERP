# Generated manually to add tariff field to Item model
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0047_add_orphaned_inventory'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='tariff',
            field=models.FloatField(default=0.0, help_text='Tariff rate (as decimal, e.g., 0.381 for 38.1%). Used for raw materials and distributed items.'),
        ),
    ]
