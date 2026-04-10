# Idempotent repair: some DBs recorded 0087 but never got ship_to_location_id (schema drift).
# Also null orphan check-in log lot_id values (e.g. after raw-SQL UNFK) so SQLite constraint checks pass.


from django.db import migrations


def _table_exists(cursor, name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=%s LIMIT 1",
        [name],
    )
    return cursor.fetchone() is not None


def repair_orphan_lot_foreign_keys(apps, schema_editor):
    """
    Remove dangling lot_id references (e.g. after raw-SQL lot delete / UNFK).
    Required so SQLite passes check_constraints() after migrations.
    """
    conn = schema_editor.connection
    if conn.vendor != 'sqlite':
        return
    with conn.cursor() as cursor:
        for tbl, sql in (
            (
                'erp_core_inventorytransaction',
                'DELETE FROM erp_core_inventorytransaction WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_lottransactionlog',
                'DELETE FROM erp_core_lottransactionlog WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_lotdepletionlog',
                'DELETE FROM erp_core_lotdepletionlog WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_lotattributechangelog',
                'DELETE FROM erp_core_lotattributechangelog WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_salesorderlot',
                'DELETE FROM erp_core_salesorderlot WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_productionbatchinput',
                'DELETE FROM erp_core_productionbatchinput WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
            (
                'erp_core_productionbatchoutput',
                'DELETE FROM erp_core_productionbatchoutput WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)',
            ),
        ):
            if _table_exists(cursor, tbl):
                cursor.execute(sql)
        if _table_exists(cursor, 'erp_core_lottraceability'):
            cursor.execute(
                """
                DELETE FROM erp_core_lottraceability
                WHERE source_lot_id NOT IN (SELECT id FROM erp_core_lot)
                   OR destination_lot_id NOT IN (SELECT id FROM erp_core_lot)
                """
            )
        if _table_exists(cursor, 'erp_core_checkinlog'):
            cursor.execute(
                """
                UPDATE erp_core_checkinlog
                SET lot_id = NULL
                WHERE lot_id IS NOT NULL
                  AND lot_id NOT IN (SELECT id FROM erp_core_lot)
                """
            )
        if _table_exists(cursor, 'erp_core_qualitytest'):
            cursor.execute(
                'DELETE FROM erp_core_qualitytest WHERE lot_id NOT IN (SELECT id FROM erp_core_lot)'
            )


def repair_salesorder_columns(apps, schema_editor):
    conn = schema_editor.connection
    table = 'erp_core_salesorder'
    with conn.cursor() as cursor:
        if conn.vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            cols = {row[1] for row in cursor.fetchall()}
            # SQLite: avoid REFERENCES on ADD COLUMN — works on all versions; ORM enforces relations.
            alters = []
            if 'ship_to_location_id' not in cols:
                alters.append(
                    'ALTER TABLE erp_core_salesorder ADD COLUMN ship_to_location_id bigint NULL'
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
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_address TEXT NULL')
            if 'customer_city' not in cols:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_city varchar(100) NULL')
            if 'customer_state' not in cols:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_state varchar(50) NULL')
            if 'customer_zip' not in cols:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_zip varchar(20) NULL')
            if 'customer_country' not in cols:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_country varchar(100) NULL')
            if 'customer_phone' not in cols:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN customer_phone varchar(50) NULL')


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0088_drop_ship_so_po'),
    ]

    operations = [
        migrations.RunPython(repair_orphan_lot_foreign_keys, migrations.RunPython.noop),
        migrations.RunPython(repair_salesorder_columns, migrations.RunPython.noop),
    ]
