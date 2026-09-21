# Generated manually — seed pigment families A–Q and backfill Item.product_family

from django.db import migrations


def forwards(apps, schema_editor):
    from erp_core.product_families import (
        backfill_item_product_families,
        seed_pigment_product_families,
    )

    seed_pigment_product_families(apps=apps)
    backfill_item_product_families(apps=apps, only_missing=False)


def backwards(apps, schema_editor):
    Item = apps.get_model("erp_core", "Item")
    RDFormulaFamily = apps.get_model("erp_core", "RDFormulaFamily")
    codes = {
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
    }
    Item.objects.filter(product_family__code__in=codes).update(product_family=None)
    # Do not delete family rows — may be referenced by R&D.


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0121_item_product_family"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
