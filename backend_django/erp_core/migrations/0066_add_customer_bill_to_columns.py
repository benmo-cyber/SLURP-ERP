# Add bill_to_* to erp_core_customer and contact_type to erp_core_customercontact
# when tables were created by view's raw SQL without these columns. Data is preserved.

from django.db import migrations, connection


def add_missing_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customer'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(erp_core_customer)")
            existing = {row[1] for row in cursor.fetchall()}
            for col_name, col_type in [
                ('bill_to_address', 'TEXT'),
                ('bill_to_city', 'VARCHAR(100)'),
                ('bill_to_state', 'VARCHAR(50)'),
                ('bill_to_zip_code', 'VARCHAR(20)'),
                ('bill_to_country', 'VARCHAR(100)'),
            ]:
                if col_name not in existing:
                    cursor.execute(f'ALTER TABLE erp_core_customer ADD COLUMN {col_name} {col_type}')
                    existing.add(col_name)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(erp_core_customercontact)")
            existing = {row[1] for row in cursor.fetchall()}
            if 'contact_type' not in existing:
                cursor.execute("ALTER TABLE erp_core_customercontact ADD COLUMN contact_type VARCHAR(20) DEFAULT 'general'")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0065_customer_bill_to_contact_type_so_invoice_contact'),
    ]

    operations = [
        migrations.RunPython(add_missing_columns, noop),
    ]
