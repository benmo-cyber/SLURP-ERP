# Generated manually for SalesOrder ship_to_location field
# Column was added directly to database via script (add_ship_to_location_field.py)
# This is a no-op migration to mark the change in migration history

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0034_add_checkout_workflow_fields'),
    ]

    operations = [
        # Column already exists in database - no operation needed
        # The ship_to_location field is defined in models.py and the column exists in the DB
    ]
