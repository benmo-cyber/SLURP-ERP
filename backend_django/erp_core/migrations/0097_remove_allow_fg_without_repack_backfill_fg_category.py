from django.db import migrations


def backfill_finished_good_category_from_siblings(apps, schema_editor):
    """Copy product_category from another Item row with the same SKU (e.g. raw/distributed) when FG row was blank."""
    Item = apps.get_model('erp_core', 'Item')
    valid = {'natural_colors', 'synthetic_colors', 'antioxidants', 'other'}
    for fg in Item.objects.filter(item_type='finished_good').iterator():
        if fg.product_category:
            continue
        sib = (
            Item.objects.filter(sku=fg.sku)
            .exclude(pk=fg.pk)
            .exclude(product_category__isnull=True)
            .exclude(product_category='')
            .first()
        )
        if sib and (sib.product_category or '') in valid:
            fg.product_category = sib.product_category
            fg.save(update_fields=['product_category'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0096_item_allow_fg_without_repack'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='item',
            name='allow_fg_without_repack',
        ),
        migrations.RunPython(backfill_finished_good_category_from_siblings, noop_reverse),
    ]
