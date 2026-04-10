# Repair drifted DBs: django_migrations may list 0015 as applied while actual_ship_date column is missing.

from django.db import migrations


def add_actual_ship_date_if_missing(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor
    table = 'erp_core_salesorder'
    column = 'actual_ship_date'
    with connection.cursor() as cursor:
        if vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            cols = [row[1] for row in cursor.fetchall()]
            if column not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN {column} datetime NULL'
                )
        elif vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            if not cursor.fetchone():
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN {column} TIMESTAMP WITH TIME ZONE NULL'
                )


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0079_vendorcontact_title'),
    ]

    operations = [
        migrations.RunPython(add_actual_ship_date_if_missing, migrations.RunPython.noop),
    ]
