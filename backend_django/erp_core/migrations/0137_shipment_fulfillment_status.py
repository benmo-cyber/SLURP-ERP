from django.db import migrations, models
import django.utils.timezone


def mark_existing_shipments_picked_up(apps, schema_editor):
    Shipment = apps.get_model("erp_core", "Shipment")
    Shipment.objects.all().update(
        fulfillment_status="picked_up",
        picked_up_at=django.utils.timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0136_salesorder_customer_required_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="shipment",
            name="fulfillment_status",
            field=models.CharField(
                choices=[("ready", "Ready for pickup"), ("picked_up", "Picked up")],
                db_index=True,
                default="ready",
                help_text="ready = staged with packing docs; picked_up = left dock (invoice created).",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="shipment",
            name="picked_up_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the carrier actually picked up; inventory depletes and draft invoice is created then.",
                null=True,
            ),
        ),
        migrations.RunPython(mark_existing_shipments_picked_up, migrations.RunPython.noop),
    ]
