# Add depleted_at to Lot; hide depleted lots from inventory after 24h

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0062_lot_pack_size_id_if_missing'),
    ]

    operations = [
        migrations.AddField(
            model_name='lot',
            name='depleted_at',
            field=models.DateTimeField(blank=True, help_text='When quantity_remaining reached 0; lots are hidden from inventory table 24h after this.', null=True),
        ),
    ]
