# State-only: add Customer, ShipToLocation, CustomerContact to migration state.
# Tables may already exist in DB; this fixes KeyError when 0065 adds fields.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0064_item_product_category'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Customer',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('customer_id', models.CharField(db_index=True, help_text='Unique customer identifier', max_length=100, unique=True)),
                        ('name', models.CharField(max_length=255)),
                        ('contact_name', models.CharField(blank=True, max_length=255, null=True)),
                        ('email', models.EmailField(blank=True, max_length=254, null=True)),
                        ('phone', models.CharField(blank=True, max_length=50, null=True)),
                        ('address', models.TextField(blank=True, help_text='Headquarters street address', null=True)),
                        ('city', models.CharField(blank=True, help_text='Headquarters city', max_length=100, null=True)),
                        ('state', models.CharField(blank=True, help_text='Headquarters state', max_length=50, null=True)),
                        ('zip_code', models.CharField(blank=True, help_text='Headquarters ZIP', max_length=20, null=True)),
                        ('country', models.CharField(blank=True, default='USA', help_text='Headquarters country', max_length=100, null=True)),
                        ('bill_to_address', models.TextField(blank=True, help_text='Bill-to street address (leave blank if same as HQ)', null=True)),
                        ('bill_to_city', models.CharField(blank=True, max_length=100, null=True)),
                        ('bill_to_state', models.CharField(blank=True, max_length=50, null=True)),
                        ('bill_to_zip_code', models.CharField(blank=True, max_length=20, null=True)),
                        ('bill_to_country', models.CharField(blank=True, max_length=100, null=True)),
                        ('payment_terms', models.CharField(blank=True, help_text='Payment terms (e.g., "Net 30", "Net 15", "Due on Receipt")', max_length=50, null=True)),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('is_active', models.BooleanField(default=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'ordering': ['name'],
                    },
                ),
                migrations.CreateModel(
                    name='ShipToLocation',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('location_name', models.CharField(help_text='Name/identifier for this location (e.g., "Main Warehouse", "West Coast Facility")', max_length=255)),
                        ('contact_name', models.CharField(blank=True, max_length=255, null=True)),
                        ('email', models.EmailField(blank=True, max_length=254, null=True)),
                        ('phone', models.CharField(blank=True, max_length=50, null=True)),
                        ('address', models.TextField()),
                        ('city', models.CharField(max_length=100)),
                        ('state', models.CharField(blank=True, max_length=50, null=True)),
                        ('zip_code', models.CharField(max_length=20)),
                        ('country', models.CharField(default='USA', max_length=100)),
                        ('is_default', models.BooleanField(default=False, help_text='Default ship-to location for this customer')),
                        ('is_active', models.BooleanField(default=True)),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ship_to_locations', to='erp_core.customer')),
                    ],
                    options={
                        'ordering': ['-is_default', 'location_name'],
                        'verbose_name_plural': 'Ship-to Locations',
                    },
                ),
                migrations.CreateModel(
                    name='CustomerContact',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('first_name', models.CharField(max_length=100)),
                        ('last_name', models.CharField(max_length=100)),
                        ('title', models.CharField(blank=True, help_text='Job title/position', max_length=100, null=True)),
                        ('contact_type', models.CharField(choices=[('billing', 'Billing'), ('sales', 'Sales'), ('shipping', 'Shipping'), ('general', 'General'), ('other', 'Other')], default='general', help_text='Type of contact (e.g. Billing, Sales)', max_length=20)),
                        ('email', models.EmailField(blank=True, max_length=254, null=True)),
                        ('phone', models.CharField(blank=True, max_length=50, null=True)),
                        ('mobile', models.CharField(blank=True, max_length=50, null=True)),
                        ('is_primary', models.BooleanField(default=False, help_text='Primary contact for this customer')),
                        ('is_active', models.BooleanField(default=True)),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='erp_core.customer')),
                    ],
                    options={
                        'ordering': ['-is_primary', 'last_name', 'first_name'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
