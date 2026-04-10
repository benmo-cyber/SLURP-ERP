# Adds contact FK to SalesOrder and Invoice (Customer/CustomerContact state from 0064_add_customer_contact_state).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0064_add_customer_contact_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='contact',
            field=models.ForeignKey(blank=True, help_text='Contact for this order (e.g. billing, sales)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales_orders', to='erp_core.customercontact'),
        ),
        migrations.AddField(
            model_name='invoice',
            name='contact',
            field=models.ForeignKey(blank=True, help_text='Bill-to or primary contact for this invoice', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoices', to='erp_core.customercontact'),
        ),
    ]
