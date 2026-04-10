# Legacy erp_core_journalentry table was missing columns the ORM expects (reference_type, status, etc.).

from django.db import migrations


def add_journalentry_columns(apps, schema_editor):
    conn = schema_editor.connection
    table = 'erp_core_journalentry'
    with conn.cursor() as cursor:
        if conn.vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info({table})')
            cols = {row[1] for row in cursor.fetchall()}
            if 'reference_type' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN reference_type varchar(50) NULL'
                )
            if 'status' not in cols:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN status varchar(20) NOT NULL DEFAULT 'draft'"
                )
            if 'fiscal_period_id' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN fiscal_period_id bigint NULL '
                    f'REFERENCES erp_core_fiscalperiod (id)'
                )
            if 'posted_by' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_by varchar(100) NULL'
                )
            if 'posted_at' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_at datetime NULL'
                )
        elif conn.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                """,
                [table],
            )
            cols = {row[0] for row in cursor.fetchall()}
            if 'reference_type' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN reference_type varchar(50) NULL'
                )
            if 'status' not in cols:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN status varchar(20) NOT NULL DEFAULT 'draft'"
                )
            if 'fiscal_period_id' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN fiscal_period_id bigint NULL '
                    f'REFERENCES erp_core_fiscalperiod (id)'
                )
            if 'posted_by' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_by varchar(100) NULL'
                )
            if 'posted_at' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_at timestamp with time zone NULL'
                )
        else:
            cursor.execute(
                """
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                [table],
            )
            cols = {row[0] for row in cursor.fetchall()}
            if 'reference_type' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN reference_type varchar(50) NULL'
                )
            if 'status' not in cols:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN status varchar(20) NOT NULL DEFAULT 'draft'"
                )
            if 'fiscal_period_id' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN fiscal_period_id bigint NULL'
                )
            if 'posted_by' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_by varchar(100) NULL'
                )
            if 'posted_at' not in cols:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN posted_at datetime(6) NULL'
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0085_accountspayable_cost_category'),
    ]

    operations = [
        migrations.RunPython(add_journalentry_columns, noop),
    ]
