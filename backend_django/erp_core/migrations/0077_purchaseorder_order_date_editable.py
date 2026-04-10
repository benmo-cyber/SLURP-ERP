# Allow staff backdated PO/issue dates (remove auto_now_add on order_date)

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0076_contact_emails_list'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaseorder',
            name='order_date',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
