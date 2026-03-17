# UserProfile for ERP role (license tier) and auth

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('erp_core', '0057_formula_mixing_steps'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('viewer', 'Viewer'), ('operator', 'Operator'), ('manager', 'Manager'), ('admin', 'Admin')],
                    default='viewer',
                    help_text='Access tier: Viewer (read-only), Operator, Manager, Admin (full).',
                    max_length=20,
                )),
                ('user', models.OneToOneField(
                    on_delete=models.CASCADE,
                    related_name='erp_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'erp_core_userprofile',
            },
        ),
    ]
