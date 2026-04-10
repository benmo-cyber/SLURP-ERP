# Add incoterms place/point to CustomerPricing (e.g. "New York" for CIF New York)

from django.db import migrations, connection


def add_incoterms_place_column(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerpricing'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(erp_core_customerpricing)")
        existing = {row[1] for row in cursor.fetchall()}
        if 'incoterms_place' not in existing:
            cursor.execute("ALTER TABLE erp_core_customerpricing ADD COLUMN incoterms_place VARCHAR(100)")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0068_customerpricing_incoterms'),
    ]

    operations = [
        migrations.RunPython(add_incoterms_place_column, noop),
    ]
