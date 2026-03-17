# Critical control points (CCP) for batch ticket pre-production checks

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0058_userprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='CriticalControlPoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. 20 mesh screen, 40 mesh screen', max_length=255)),
                ('display_order', models.PositiveSmallIntegerField(default=0, help_text='Order in dropdowns (lower first)')),
            ],
            options={
                'ordering': ['display_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='formula',
            name='critical_control_point',
            field=models.ForeignKey(
                blank=True,
                help_text='CCP shown on batch ticket pre-production checks (e.g. Has [CCP] been inspected and installed properly?)',
                null=True,
                on_delete=models.SET_NULL,
                related_name='formulas',
                to='erp_core.criticalcontrolpoint',
            ),
        ),
    ]
