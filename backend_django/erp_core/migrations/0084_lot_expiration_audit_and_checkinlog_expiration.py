# Generated manually for expiration date on check-in log + lot attribute audit trail

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0083_add_checkinlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='checkinlog',
            name='expiration_date',
            field=models.DateTimeField(blank=True, help_text='Expiration date recorded at check-in (snapshot)', null=True),
        ),
        migrations.CreateModel(
            name='LotAttributeChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_name', models.CharField(db_index=True, max_length=64)),
                ('old_value', models.TextField(blank=True, default='')),
                ('new_value', models.TextField(blank=True, default='')),
                ('reason', models.CharField(blank=True, default='', max_length=500)),
                ('changed_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('changed_by', models.CharField(blank=True, default='', max_length=255)),
                ('lot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attribute_change_logs', to='erp_core.lot')),
            ],
            options={
                'verbose_name': 'Lot attribute change log',
                'verbose_name_plural': 'Lot attribute change logs',
                'ordering': ['-changed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='lotattributechangelog',
            index=models.Index(fields=['-changed_at', 'field_name'], name='lacg_changed_field_idx'),
        ),
    ]
