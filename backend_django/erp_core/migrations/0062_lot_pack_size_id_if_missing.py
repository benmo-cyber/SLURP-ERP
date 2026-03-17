# Add pack_size_id to Lot if missing (fixes 500 when DB schema was created without it)

from django.db import migrations, connection


def add_pack_size_id_if_missing(apps, schema_editor):
    """Add pack_size_id column to erp_core_lot if it doesn't exist (e.g. older DB)."""
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(erp_core_lot)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'pack_size_id' in columns:
            return
        # SQLite: add nullable column (no FK in ALTER to avoid missing table)
        cursor.execute("ALTER TABLE erp_core_lot ADD COLUMN pack_size_id INTEGER NULL")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0061_lot_quantity_on_hold'),
    ]

    operations = [
        migrations.RunPython(add_pack_size_id_if_missing, noop_reverse),
    ]
