# Sales order order_date editable (staff God mode / historical entry)

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0077_purchaseorder_order_date_editable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='salesorder',
            name='order_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
