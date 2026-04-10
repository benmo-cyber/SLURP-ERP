from django.db import migrations, models


def set_vendor_labeled_sku(apps, schema_editor):
    Item = apps.get_model('erp_core', 'Item')
    Item.objects.filter(sku__iexact='X2410K0017').update(allow_fg_without_repack=True)


def unset_vendor_labeled_sku(apps, schema_editor):
    Item = apps.get_model('erp_core', 'Item')
    Item.objects.filter(sku__iexact='X2410K0017').update(allow_fg_without_repack=False)


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0095_ship_idempotency'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='allow_fg_without_repack',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'If True, receipt lots appear on Finished Good inventory without a closed repack/production batch '
                    '(vendor-labeled stock ready to pick). Gated categories only; see inventory_fg_visibility.'
                ),
            ),
        ),
        migrations.RunPython(set_vendor_labeled_sku, unset_vendor_labeled_sku),
    ]
