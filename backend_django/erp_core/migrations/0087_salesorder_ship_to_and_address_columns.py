# Repair drifted DBs: ORM expects ship_to_location_id and legacy address columns on erp_core_salesorder.

from django.db import migrations


def add_salesorder_columns_if_missing(apps, schema_editor):
    conn = schema_editor.connection
    table = 'erp_core_salesorder'
    with conn.cursor() as cursor:
        if conn.vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            cols = {row[1] for row in cursor.fetchall()}
            alters = []
            if 'ship_to_location_id' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN ship_to_location_id bigint NULL '
                    'REFERENCES erp_core_shiptolocation (id)'
                )
            if 'customer_legacy_id' not in cols:
                alters.append(
                    "ALTER TABLE erp_core_salesorder ADD COLUMN customer_legacy_id varchar(100) NULL"
                )
            if 'customer_address' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_address TEXT NULL'
                )
            if 'customer_city' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_city varchar(100) NULL'
                )
            if 'customer_state' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_state varchar(50) NULL'
                )
            if 'customer_zip' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_zip varchar(20) NULL'
                )
            if 'customer_country' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_country varchar(100) NULL'
                )
            if 'customer_phone' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN customer_phone varchar(50) NULL'
                )
            for sql in alters:
                cursor.execute(sql)
        elif conn.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                [table],
            )
            cols = {row[0] for row in cursor.fetchall()}
            if 'ship_to_location_id' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN ship_to_location_id bigint NULL '
                    f'REFERENCES erp_core_shiptolocation (id)'
                )
            if 'customer_legacy_id' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_legacy_id varchar(100) NULL'
                )
            if 'customer_address' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_address TEXT NULL'
                )
            if 'customer_city' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_city varchar(100) NULL'
                )
            if 'customer_state' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_state varchar(50) NULL'
                )
            if 'customer_zip' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_zip varchar(20) NULL'
                )
            if 'customer_country' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_country varchar(100) NULL'
                )
            if 'customer_phone' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN customer_phone varchar(50) NULL'
                )


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0086_journalentry_schema_columns'),
    ]

    operations = [
        migrations.RunPython(add_salesorder_columns_if_missing, migrations.RunPython.noop),
    ]
