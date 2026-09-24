# Generated manually for CustomerRMA / staging lot fields / hold kind

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0143_lot_shelf_life_extension"),
    ]

    operations = [
        migrations.CreateModel(
            name="RmaNumberSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year_prefix", models.CharField(max_length=2, unique=True)),
                ("sequence_number", models.IntegerField(default=0)),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-year_prefix", "-sequence_number"],
            },
        ),
        migrations.AddField(
            model_name="lot",
            name="rma_number",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Customer RMA number when this lot was created by RMA check-in (staging -R lot).",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="lot",
            name="source_lot",
            field=models.ForeignKey(
                blank=True,
                help_text="Original shipped lot this RMA staging lot will merge into on accept.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="return_staging_lots",
                to="erp_core.lot",
            ),
        ),
        migrations.AlterField(
            model_name="lotholdcase",
            name="kind",
            field=models.CharField(
                choices=[
                    ("receiving", "Receiving / investigation"),
                    ("awaiting_micro", "Awaiting micro / QC"),
                    ("customer_return", "Customer return / RMA"),
                ],
                db_index=True,
                default="receiving",
                help_text=(
                    "receiving = inbound issue; awaiting_micro = manufactured lot pending QC release; "
                    "customer_return = RMA staging lot pending investigation."
                ),
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="CustomerRma",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rma_number", models.CharField(db_index=True, max_length=32, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("partially_received", "Partially received"),
                            ("received", "Received"),
                            ("closed", "Closed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=32,
                    ),
                ),
                ("reason", models.TextField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                ("opened_by", models.CharField(blank=True, default="", max_length=150)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "credit_invoice",
                    models.ForeignKey(
                        blank=True,
                        help_text="Credit memo issued when this RMA was opened.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rma_credits",
                        to="erp_core.invoice",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rmas",
                        to="erp_core.customer",
                    ),
                ),
                (
                    "sales_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rmas",
                        to="erp_core.salesorder",
                    ),
                ),
            ],
            options={
                "verbose_name": "Customer RMA",
                "verbose_name_plural": "Customer RMAs",
                "ordering": ["-opened_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomerRmaLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_requested", models.FloatField()),
                ("quantity_received", models.FloatField(default=0.0)),
                (
                    "unit_price",
                    models.FloatField(help_text="Unit price used for the credit memo line."),
                ),
                (
                    "rma",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="erp_core.customerrma",
                    ),
                ),
                (
                    "sales_order_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rma_lines",
                        to="erp_core.salesorderitem",
                    ),
                ),
                (
                    "source_lot",
                    models.ForeignKey(
                        help_text="Original lot that was shipped to the customer.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rma_source_lines",
                        to="erp_core.lot",
                    ),
                ),
                (
                    "staging_lot",
                    models.ForeignKey(
                        blank=True,
                        help_text="Current/last RMA staging (-R) lot created at check-in.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rma_staging_for_lines",
                        to="erp_core.lot",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
