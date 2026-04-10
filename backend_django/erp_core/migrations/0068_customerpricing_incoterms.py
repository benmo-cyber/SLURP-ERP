# Add incoterms to CustomerPricing (per-item). Table may exist from view's raw SQL.

from django.db import migrations, connection


def add_incoterms_column(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customerpricing'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(erp_core_customerpricing)")
        existing = {row[1] for row in cursor.fetchall()}
        if 'incoterms' not in existing:
            cursor.execute("ALTER TABLE erp_core_customerpricing ADD COLUMN incoterms VARCHAR(30)")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0067_customercontact_ap_purchasing_contact'),
    ]

    operations = [
        migrations.RunPython(add_incoterms_column, noop),
    ]
