# Actual cost tracking on AP: freight total, tariff/duties paid, shipment method (air/sea)

from django.db import migrations, connection


def add_ap_actual_cost_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_accountspayable'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(erp_core_accountspayable)")
        existing = {row[1] for row in cursor.fetchall()}
        if 'freight_total' not in existing:
            cursor.execute("ALTER TABLE erp_core_accountspayable ADD COLUMN freight_total REAL NULL")
        if 'tariff_duties_paid' not in existing:
            cursor.execute("ALTER TABLE erp_core_accountspayable ADD COLUMN tariff_duties_paid REAL NULL")
        if 'shipment_method' not in existing:
            cursor.execute("ALTER TABLE erp_core_accountspayable ADD COLUMN shipment_method VARCHAR(20) NULL")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0070_costmaster_incoterms_place'),
    ]

    operations = [
        migrations.RunPython(add_ap_actual_cost_columns, noop),
    ]
