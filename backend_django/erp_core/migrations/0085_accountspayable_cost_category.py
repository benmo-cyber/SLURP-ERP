# AccountsPayable existed in code/DB without a CreateModel in the graph (0071 only used raw SQL).
# JournalEntry / FiscalPeriod were removed in 0019 and never re-added to the graph; AP FKs need them in state.
# State: register FiscalPeriod, JournalEntry, JournalEntryLine, AccountsPayable (+ cost_category).
# DB: add cost_category on erp_core_accountspayable only (other tables assumed to exist).

from django.db import migrations, models
import django.db.models.deletion


def add_cost_category_column(apps, schema_editor):
    connection = schema_editor.connection
    table = 'erp_core_accountspayable'
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [table]
            )
            if not cursor.fetchone():
                return
            cursor.execute(f'PRAGMA table_info({table})')
            existing = {row[1] for row in cursor.fetchall()}
            if 'cost_category' not in existing:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN cost_category varchar(20) NOT NULL DEFAULT ""'
                )
        elif connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = current_schema() AND table_name = %s
                )
                """,
                [table],
            )
            if not cursor.fetchone()[0]:
                return
            cursor.execute(
                f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS cost_category varchar(20) NOT NULL DEFAULT '';
                """
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
                """,
                [table, 'cost_category'],
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    f'ALTER TABLE {table} ADD COLUMN cost_category varchar(20) NOT NULL DEFAULT \'\''
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0084_lot_expiration_audit_and_checkinlog_expiration'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_cost_category_column, noop),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='FiscalPeriod',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        (
                            'period_name',
                            models.CharField(
                                help_text='e.g., "2024-01" for January 2024',
                                max_length=50,
                                unique=True,
                            ),
                        ),
                        ('start_date', models.DateField()),
                        ('end_date', models.DateField()),
                        ('is_closed', models.BooleanField(default=False, help_text='Whether this period has been closed')),
                        ('closed_date', models.DateTimeField(blank=True, null=True)),
                        ('closed_by', models.CharField(blank=True, max_length=100, null=True)),
                        ('notes', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'ordering': ['-start_date'],
                    },
                ),
                migrations.AddIndex(
                    model_name='fiscalperiod',
                    index=models.Index(fields=['start_date', 'end_date'], name='erp_core_fp_dates_idx'),
                ),
                migrations.AddIndex(
                    model_name='fiscalperiod',
                    index=models.Index(fields=['is_closed'], name='erp_core_fp_closed_idx'),
                ),
                migrations.CreateModel(
                    name='JournalEntry',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        (
                            'entry_number',
                            models.CharField(
                                db_index=True,
                                help_text='Auto-generated journal entry number',
                                max_length=100,
                                unique=True,
                            ),
                        ),
                        ('entry_date', models.DateField(db_index=True)),
                        ('description', models.TextField()),
                        (
                            'reference_number',
                            models.CharField(
                                blank=True,
                                help_text='Reference to source document (PO, SO, Invoice, etc.)',
                                max_length=100,
                                null=True,
                            ),
                        ),
                        (
                            'reference_type',
                            models.CharField(
                                blank=True,
                                help_text='Type of reference (invoice, purchase_order, sales_order, manual, etc.)',
                                max_length=50,
                                null=True,
                            ),
                        ),
                        (
                            'status',
                            models.CharField(
                                choices=[
                                    ('draft', 'Draft'),
                                    ('posted', 'Posted'),
                                    ('reversed', 'Reversed'),
                                ],
                                default='draft',
                                max_length=20,
                            ),
                        ),
                        (
                            'fiscal_period',
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name='journal_entries',
                                to='erp_core.fiscalperiod',
                            ),
                        ),
                        ('created_by', models.CharField(blank=True, max_length=100, null=True)),
                        ('posted_by', models.CharField(blank=True, max_length=100, null=True)),
                        ('posted_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name_plural': 'Journal Entries',
                        'ordering': ['-entry_date', '-created_at'],
                    },
                ),
                migrations.AddIndex(
                    model_name='journalentry',
                    index=models.Index(fields=['entry_date', 'status'], name='erp_core_je_date_st_idx'),
                ),
                migrations.AddIndex(
                    model_name='journalentry',
                    index=models.Index(fields=['reference_number', 'reference_type'], name='erp_core_je_ref_idx'),
                ),
                migrations.AddIndex(
                    model_name='journalentry',
                    index=models.Index(fields=['fiscal_period', 'entry_date'], name='erp_core_je_fp_date_idx'),
                ),
                migrations.CreateModel(
                    name='JournalEntryLine',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        (
                            'journal_entry',
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name='lines',
                                to='erp_core.journalentry',
                            ),
                        ),
                        (
                            'account',
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name='journal_lines',
                                to='erp_core.account',
                            ),
                        ),
                        (
                            'debit_credit',
                            models.CharField(
                                choices=[('debit', 'Debit'), ('credit', 'Credit')],
                                max_length=10,
                            ),
                        ),
                        ('amount', models.FloatField()),
                        ('description', models.CharField(blank=True, max_length=255, null=True)),
                    ],
                    options={
                        'ordering': ['id'],
                    },
                ),
                migrations.AddIndex(
                    model_name='journalentryline',
                    index=models.Index(fields=['account', 'journal_entry'], name='erp_core_jel_ac_je_idx'),
                ),
                migrations.AddIndex(
                    model_name='journalentryline',
                    index=models.Index(fields=['journal_entry', 'debit_credit'], name='erp_core_jel_je_dc_idx'),
                ),
                migrations.CreateModel(
                    name='AccountsPayable',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('vendor_name', models.CharField(db_index=True, help_text='Vendor name', max_length=255)),
                        ('vendor_id', models.CharField(blank=True, help_text='Vendor ID if available', max_length=100, null=True)),
                        (
                            'purchase_order',
                            models.ForeignKey(
                                blank=True,
                                help_text='Related purchase order',
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name='ap_entries',
                                to='erp_core.purchaseorder',
                            ),
                        ),
                        ('invoice_number', models.CharField(blank=True, help_text='Vendor invoice number', max_length=100, null=True)),
                        ('invoice_date', models.DateField(help_text='Date of vendor invoice')),
                        ('due_date', models.DateField(help_text='Payment due date')),
                        ('original_amount', models.FloatField(help_text='Original invoice amount')),
                        ('amount_paid', models.FloatField(default=0.0, help_text='Amount paid so far')),
                        ('balance', models.FloatField(help_text='Outstanding balance (original_amount - amount_paid)')),
                        (
                            'status',
                            models.CharField(
                                choices=[
                                    ('open', 'Open'),
                                    ('partial', 'Partially Paid'),
                                    ('paid', 'Paid'),
                                    ('overdue', 'Overdue'),
                                    ('cancelled', 'Cancelled'),
                                ],
                                default='open',
                                max_length=20,
                            ),
                        ),
                        (
                            'account',
                            models.ForeignKey(
                                blank=True,
                                help_text='AP account',
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name='ap_entries',
                                to='erp_core.account',
                            ),
                        ),
                        (
                            'journal_entry',
                            models.ForeignKey(
                                blank=True,
                                help_text='Journal entry created for this AP',
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name='ap_entries',
                                to='erp_core.journalentry',
                            ),
                        ),
                        ('notes', models.TextField(blank=True, null=True)),
                        (
                            'cost_category',
                            models.CharField(
                                blank=True,
                                choices=[
                                    ('', 'Legacy / unspecified'),
                                    ('material', 'Material — vendor goods invoice (COGS)'),
                                    ('freight', 'Freight — shipping / logistics invoice'),
                                    ('duty_tax', 'Duty & tax — CBP, customs, broker'),
                                ],
                                default='',
                                help_text='For landed cost: classify this AP line (link same PO on vendor, freight, and duty invoices).',
                                max_length=20,
                            ),
                        ),
                        (
                            'freight_total',
                            models.FloatField(
                                blank=True,
                                help_text='Actual total freight on this invoice/shipment (spread over quantity for unit cost)',
                                null=True,
                            ),
                        ),
                        (
                            'tariff_duties_paid',
                            models.FloatField(blank=True, help_text='Duties/tariff paid at import for this shipment', null=True),
                        ),
                        (
                            'shipment_method',
                            models.CharField(
                                blank=True,
                                choices=[('air', 'Air'), ('sea', 'Sea')],
                                help_text='Method of shipment (air vs sea)',
                                max_length=20,
                                null=True,
                            ),
                        ),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name_plural': 'Accounts Payable',
                        'ordering': ['due_date', 'vendor_name'],
                    },
                ),
                migrations.AddIndex(
                    model_name='accountspayable',
                    index=models.Index(fields=['vendor_name', 'status'], name='erp_core_ac_vendor_st_idx'),
                ),
                migrations.AddIndex(
                    model_name='accountspayable',
                    index=models.Index(fields=['due_date', 'status'], name='erp_core_ac_due_st_idx'),
                ),
                migrations.AddIndex(
                    model_name='accountspayable',
                    index=models.Index(fields=['purchase_order', 'status'], name='erp_core_ac_po_st_idx'),
                ),
            ],
        ),
    ]
