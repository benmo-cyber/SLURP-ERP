# Add A/P contact and Purchasing contact flags to CustomerContact

from django.db import migrations, connection


def add_ap_purchasing_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(erp_core_customercontact)")
        existing = {row[1] for row in cursor.fetchall()}
        if 'is_ap_contact' not in existing:
            cursor.execute("ALTER TABLE erp_core_customercontact ADD COLUMN is_ap_contact BOOLEAN DEFAULT 0")
        if 'is_purchasing_contact' not in existing:
            cursor.execute("ALTER TABLE erp_core_customercontact ADD COLUMN is_purchasing_contact BOOLEAN DEFAULT 0")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0066_add_customer_bill_to_columns'),
    ]

    operations = [
        migrations.RunPython(add_ap_purchasing_columns, noop),
    ]
