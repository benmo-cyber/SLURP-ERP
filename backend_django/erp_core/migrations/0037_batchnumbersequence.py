# Generated manually for BatchNumberSequence model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0035_vendorpricing'),
    ]

    operations = [
        migrations.CreateModel(
            name='BatchNumberSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_prefix', models.CharField(db_index=True, max_length=8, unique=True)),
                ('sequence_number', models.IntegerField(default=0)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-date_prefix', '-sequence_number'],
            },
        ),
    ]
