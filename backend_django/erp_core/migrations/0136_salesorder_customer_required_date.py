from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erp_core", "0135_coa_test_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorder",
            name="customer_required_date",
            field=models.DateField(
                blank=True,
                help_text="Date the customer needs the goods (customer required / CRD).",
                null=True,
            ),
        ),
    ]
