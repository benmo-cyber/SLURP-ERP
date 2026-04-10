from django.db import models
from django.utils import timezone
from django.conf import settings


class Item(models.Model):
    ITEM_TYPE_CHOICES = [
        ('raw_material', 'Raw Material'),
        ('distributed_item', 'Distributed Item'),
        ('finished_good', 'Finished Good'),
        ('indirect_material', 'Indirect Material'),
    ]
    PRODUCT_CATEGORY_CHOICES = [
        ('natural_colors', 'Natural Colors'),
        ('synthetic_colors', 'Synthetic Colors'),
        ('antioxidants', 'Antioxidants'),
        ('other', 'Other'),
    ]
    
    UNIT_CHOICES = [
        ('lbs', 'Pounds'),
        ('kg', 'Kilograms'),
        ('ea', 'Each'),
    ]
    
    sku = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255, help_text='WWI Item Name - used for sales orders and internal reference')
    vendor_item_name = models.CharField(max_length=255, blank=True, null=True, help_text='Vendor Item Name - used in purchase orders to vendors')
    vendor_item_number = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Vendor catalog / part number (shown on POs and item lists next to vendor name).",
    )
    description = models.TextField(blank=True, null=True)
    item_type = models.CharField(max_length=50, choices=ITEM_TYPE_CHOICES)
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES)
    vendor = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    pack_size = models.FloatField(blank=True, null=True, help_text='Legacy field - use ItemPackSize model instead')
    price = models.FloatField(blank=True, null=True, help_text='Legacy field - use ItemPackSize model instead')
    tariff = models.FloatField(default=0.0, help_text='Tariff rate (as decimal, e.g., 0.381 for 38.1%). Used for raw materials and distributed items.')
    hts_code = models.CharField(max_length=50, blank=True, null=True, help_text='HTS (Harmonized Tariff Schedule) code for tariff calculation')
    country_of_origin = models.CharField(max_length=255, blank=True, null=True, help_text='Country of origin for tariff calculation')
    on_order = models.FloatField(default=0.0, help_text='Quantity currently on order')
    approved_for_formulas = models.BooleanField(default=False)
    product_category = models.CharField(
        max_length=50,
        choices=PRODUCT_CATEGORY_CHOICES,
        blank=True,
        null=True,
        help_text='Product category: Natural Colors, Synthetic Colors, Antioxidants, or Other'
    )
    # Parent / pack variant (pigment SKUs: letter + material code; optional L/K + 4-digit pack suffix)
    sku_parent_code = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text='Material family code (e.g. D1307, P2408). Set automatically from SKU when parseable.',
    )
    sku_pack_suffix = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text='Pack segment when present, e.g. L0040 or K0920. Null for master / parent-only rows.',
    )
    sku_parent_item = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sku_variant_items',
        help_text='Optional link to the master item row for this family (same vendor when possible).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sku', 'vendor']
        unique_together = [['sku', 'vendor']]
    
    def __str__(self):
        return f"{self.sku} - {self.name}"


class ItemPackSize(models.Model):
    """Represents different pack sizes available for an item (e.g., 2000lb IBC, 5 gallon pail)"""
    PACK_SIZE_UNIT_CHOICES = [
        ('lbs', 'Pounds'),
        ('kg', 'Kilograms'),
        ('gal', 'Gallons'),
        ('ea', 'Each'),
        ('pcs', 'Pieces'),
    ]
    
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='pack_sizes')
    pack_size = models.FloatField(help_text='Pack size value (e.g., 2000, 5)')
    pack_size_unit = models.CharField(max_length=10, choices=PACK_SIZE_UNIT_CHOICES, help_text='Unit for pack size (e.g., lbs, gal)')
    price = models.FloatField(blank=True, null=True, help_text='Price per pack (optional, pack-size-specific pricing)')
    description = models.CharField(max_length=255, blank=True, null=True, help_text='Description of pack size (e.g., "2000lb IBC", "5 gallon pail")')
    is_default = models.BooleanField(default=False, help_text='Default pack size for this item')
    is_active = models.BooleanField(default=True, help_text='Whether this pack size is currently available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['item', 'pack_size', 'pack_size_unit']
        unique_together = [['item', 'pack_size', 'pack_size_unit']]
        verbose_name = 'Item Pack Size'
        verbose_name_plural = 'Item Pack Sizes'
    
    def __str__(self):
        return f"{self.item.sku} - {self.pack_size} {self.pack_size_unit}"


class FinishedProductSpecification(models.Model):
    """Finished Product Specification (FPS) data for finished goods"""
    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name='fps', limit_choices_to={'item_type': 'finished_good'})
    
    # Basic Information
    product_description = models.TextField(blank=True, null=True, help_text='Physical state, color, odor, etc.')
    color_specification = models.TextField(blank=True, null=True, help_text='CV, dye %, color strength, etc.')
    ph = models.CharField(max_length=50, blank=True, null=True)
    water_activity = models.CharField(max_length=50, blank=True, null=True, help_text='aW')
    microbiological_requirements = models.TextField(blank=True, null=True, help_text='If micro testing not required, rationale must be provided')
    shelf_life_storage = models.TextField(blank=True, null=True, help_text='Temperature data, Basis for decision, Shelf-Life Assignment Form (Doc No. 5.1.4–03), Shelf-Life Study Log (Doc No. 5.1.4–02)')
    packaging_type = models.CharField(max_length=255, blank=True, null=True)
    additional_criteria = models.TextField(blank=True, null=True, help_text='Physical parameter testing, flavor profile, customer considerations, etc.')
    
    # Checklist
    msds_created = models.BooleanField(default=False)
    commercial_spec_created = models.BooleanField(default=False, help_text='COA')
    label_template_created = models.BooleanField(default=False)
    micro_growth_evaluated = models.BooleanField(default=False)
    kosher_letter_added = models.BooleanField(default=False)
    haccp_plan_created = models.BooleanField(default=False)
    processing_requirements = models.TextField(blank=True, null=True, help_text='Specific tank or mixer, mixing time, allergen considerations, temperature requirements')
    
    # Metadata
    completed_by_name = models.CharField(max_length=255, blank=True, null=True, help_text='Name and Title of Person Completing Form')
    completed_by_signature = models.CharField(max_length=255, blank=True, null=True)
    completed_date = models.DateField(blank=True, null=True)
    test_frequency = models.CharField(max_length=255, blank=True, null=True)
    
    # PDF file storage
    fps_pdf = models.FileField(upload_to='fps_pdfs/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Finished Product Specification'
        verbose_name_plural = 'Finished Product Specifications'
    
    def __str__(self):
        return f"FPS - {self.item.name}"


class LotNumberSequence(models.Model):
    """Sequence tracking for lot numbers (format: 1yy00000)"""
    year_prefix = models.CharField(max_length=2, unique=True, null=True, blank=True)  # yy
    date_prefix = models.CharField(max_length=6, unique=True, null=True, blank=True)  # Legacy field
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-year_prefix', '-sequence_number']

class PONumberSequence(models.Model):
    """Sequence tracking for PO numbers (format: 2yy000)"""
    year_prefix = models.CharField(max_length=2, unique=True)  # yy
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-year_prefix', '-sequence_number']

class SalesOrderNumberSequence(models.Model):
    """Sequence tracking for sales order numbers (format: 3yy0000)"""
    year_prefix = models.CharField(max_length=2, unique=True)  # yy
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-year_prefix', '-sequence_number']

class InvoiceNumberSequence(models.Model):
    """Sequence tracking for invoice numbers (format: 4yy0000)"""
    year_prefix = models.CharField(max_length=2, unique=True)  # yy
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-year_prefix', '-sequence_number']

class CustomerNumberSequence(models.Model):
    """Sequence tracking for customer IDs (format: 001, 002, etc.)"""
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-sequence_number']

class BatchNumberSequence(models.Model):
    """Sequence tracking for batch numbers (format: BATCH-YYYYMMDD-001)"""
    date_prefix = models.CharField(max_length=8, unique=True, db_index=True)  # YYYYMMDD
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_prefix', '-sequence_number']


class Lot(models.Model):
    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('on_hold', 'On Hold'),
    ]
    
    lot_number = models.CharField(max_length=20, unique=True, db_index=True, blank=True, null=True, help_text='Lot number - generated on batch closure, or vendor_lot_number for raw materials')
    vendor_lot_number = models.CharField(max_length=100, blank=True, null=True, help_text='Vendor lot number from check-in form')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='lots')
    pack_size = models.ForeignKey('ItemPackSize', on_delete=models.SET_NULL, null=True, blank=True, related_name='lots', help_text='Pack size for this lot')
    quantity = models.FloatField()
    quantity_remaining = models.FloatField()
    received_date = models.DateTimeField()
    manufacture_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Manufacturer production or pack date when known (common for distributed / resale goods).',
    )
    expiration_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='accepted', help_text='Acceptance status of the lot')
    on_hold = models.BooleanField(default=False, help_text='Lot is on hold and not available for use (deprecated - use status instead)')
    quantity_on_hold = models.FloatField(default=0.0, help_text='Amount of this lot on hold (not available). Use for partial holds.')
    freight_actual = models.FloatField(blank=True, null=True, help_text='Actual freight cost for this lot')
    po_number = models.CharField(max_length=100, blank=True, null=True, help_text='Purchase order number associated with this lot')
    short_reason = models.CharField(max_length=255, blank=True, null=True, help_text='Reason for short shipment (damage, short shipped, etc.)')
    created_at = models.DateTimeField(auto_now_add=True)
    depleted_at = models.DateTimeField(blank=True, null=True, help_text='When quantity_remaining reached 0; lots are hidden from inventory table 24h after this.')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.lot_number
    
    def save(self, *args, **kwargs):
        from django.utils import timezone
        if self.quantity_remaining <= 0 and self.depleted_at is None:
            self.depleted_at = timezone.now()
        elif self.quantity_remaining > 0:
            self.depleted_at = None
        super().save(*args, **kwargs)


class ItemCoaTestLine(models.Model):
    """
    Per-item COA / micro test rows (Test + Specification columns on the certificate).
    Used when releasing manufactured lots from hold and for PDF generation.
    """
    RESULT_KIND_CHOICES = [
        ('numeric_range', 'Numeric range (min–max)'),
        ('numeric_minimum', 'Numeric minimum (e.g. NLT)'),
        ('pass_fail', 'Pass / fail (text)'),
        ('text_only', 'Text only (no auto pass/fail)'),
    ]

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='coa_test_lines',
        limit_choices_to={'item_type__in': ['finished_good', 'distributed_item']},
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    test_name = models.CharField(max_length=255)
    specification_text = models.TextField(help_text='Shown in the COA Specification column')
    result_kind = models.CharField(max_length=32, choices=RESULT_KIND_CHOICES, default='text_only')
    numeric_min = models.FloatField(blank=True, null=True, help_text='For numeric_minimum or numeric_range')
    numeric_max = models.FloatField(blank=True, null=True, help_text='For numeric_range only')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['item', 'sort_order', 'id']
        verbose_name = 'Item COA test line'
        verbose_name_plural = 'Item COA test lines'

    def __str__(self):
        return f"{self.item.sku} — {self.test_name}"


class LotCoaCertificate(models.Model):
    """Master COA for a manufactured lot (micro/QC recorded at full release from hold).

    Customer name and PO are not stored here; use LotCoaCustomerCopy per sales allocation.
    Legacy rows may still have customer_name / customer_po populated.
    """
    lot = models.OneToOneField(Lot, on_delete=models.CASCADE, related_name='coa_certificate')
    customer_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Deprecated: use customer-specific COAs on sales allocations.',
    )
    customer_po = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text='Deprecated: use customer-specific COAs on sales allocations.',
    )
    quantity_snapshot = models.FloatField(
        blank=True,
        null=True,
        help_text='Lot quantity (item UOM) shown on master COA PDF at issue time',
    )
    qc_parameter_name_snapshot = models.CharField(max_length=255, blank=True, default='')
    qc_spec_min_snapshot = models.FloatField(blank=True, null=True)
    qc_spec_max_snapshot = models.FloatField(blank=True, null=True)
    qc_result_value = models.FloatField(blank=True, null=True)
    qc_result_pass = models.BooleanField(blank=True, null=True)
    coa_pdf = models.FileField(upload_to='coa_pdfs/', blank=True, null=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    recorded_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = 'Lot COA certificate'
        verbose_name_plural = 'Lot COA certificates'
        ordering = ['-issued_at']

    def __str__(self):
        return f"COA {self.lot.lot_number or self.lot_id}"


class LotCoaCustomerCopy(models.Model):
    """Customer-facing COA PDF for one lot allocation (lot + sales order line + qty)."""

    certificate = models.ForeignKey(
        LotCoaCertificate,
        on_delete=models.CASCADE,
        related_name='customer_copies',
    )
    sales_order_lot = models.OneToOneField(
        'SalesOrderLot',
        on_delete=models.CASCADE,
        related_name='coa_customer_copy',
    )
    customer_name = models.CharField(max_length=255, blank=True, default='')
    customer_po = models.CharField(max_length=120, blank=True, default='')
    quantity_snapshot = models.FloatField(
        help_text='Allocated quantity (item UOM) shown on this COA',
    )
    coa_pdf = models.FileField(upload_to='coa_pdfs/customer/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lot COA (customer copy)'
        verbose_name_plural = 'Lot COA customer copies'

    def __str__(self):
        so = self.sales_order_lot.sales_order_item.sales_order.so_number
        ln = self.certificate.lot.lot_number or str(self.certificate.lot_id)
        return f"COA {ln} → {so}"


class LotCoaLineResult(models.Model):
    """One analysis row on a lot COA (micro or other tests)."""
    certificate = models.ForeignKey(LotCoaCertificate, on_delete=models.CASCADE, related_name='line_results')
    item_line = models.ForeignKey(
        ItemCoaTestLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lot_results',
    )
    test_name = models.CharField(max_length=255)
    specification_text = models.TextField()
    result_text = models.CharField(max_length=500)
    passes = models.BooleanField(blank=True, null=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Lot COA line result'
        verbose_name_plural = 'Lot COA line results'

    def __str__(self):
        return f"{self.test_name}: {self.result_text}"


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('receipt', 'Receipt'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
        ('production', 'Production'),
        ('production_input', 'Production Input'),
        ('production_output', 'Production Output'),
        ('repack_input', 'Repack Input'),
        ('repack_output', 'Repack Output'),
        ('indirect_material_consumption', 'Indirect Material Consumption'),
        ('indirect_material_checkout', 'Indirect Material Checkout'),
    ]
    
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='inventory_transactions')
    quantity = models.FloatField()
    transaction_date = models.DateTimeField(auto_now_add=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-transaction_date']


class LotTransactionLog(models.Model):
    """Logs ALL lot quantity transactions, not just depletions"""
    TRANSACTION_TYPE_CHOICES = [
        ('receipt', 'Receipt'),
        ('production_input', 'Production Input'),
        ('production_output', 'Production Output'),
        ('repack_input', 'Repack Input'),
        ('repack_output', 'Repack Output'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
        ('allocation', 'Allocation'),
        ('deallocation', 'Deallocation'),
        ('manual', 'Manual'),
        ('reversal', 'Reversal/Cancellation'),
        ('indirect_material_consumption', 'Indirect Material Consumption'),
        ('indirect_material_checkout', 'Indirect Material Checkout'),
    ]
    
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='transaction_logs')
    lot_number = models.CharField(max_length=20, db_index=True, help_text='Snapshot of lot number at time of transaction')
    item_sku = models.CharField(max_length=255, db_index=True, help_text='Item SKU at time of transaction')
    item_name = models.CharField(max_length=255, help_text='Item name at time of transaction')
    vendor = models.CharField(max_length=255, blank=True, null=True, help_text='Vendor at time of transaction')
    
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES, help_text='Type of transaction')
    quantity_before = models.FloatField(help_text='Quantity remaining before this transaction')
    quantity_change = models.FloatField(help_text='Quantity change (positive for additions, negative for reductions)')
    quantity_after = models.FloatField(help_text='Quantity remaining after this transaction')
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs', help_text='Unit of measure for quantities')
    
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text='Batch number, SO number, PO number, etc.')
    reference_type = models.CharField(max_length=50, blank=True, null=True, help_text='Type of reference (batch_number, so_number, po_number, etc.)')
    
    transaction_id = models.IntegerField(blank=True, null=True, help_text='Related InventoryTransaction ID if applicable')
    batch_id = models.IntegerField(blank=True, null=True, help_text='Related ProductionBatch ID if applicable')
    sales_order_id = models.IntegerField(blank=True, null=True, help_text='Related SalesOrder ID if applicable')
    purchase_order_id = models.IntegerField(blank=True, null=True, help_text='Related PurchaseOrder ID if applicable')
    
    notes = models.TextField(blank=True, null=True, help_text='Additional context about the transaction')
    logged_at = models.DateTimeField(auto_now_add=True, db_index=True)
    logged_by = models.CharField(max_length=255, blank=True, null=True, help_text='User who performed the transaction')
    
    class Meta:
        ordering = ['-logged_at']
        verbose_name = 'Lot Transaction Log'
        verbose_name_plural = 'Lot Transaction Logs'
        indexes = [
            models.Index(fields=['-logged_at', 'lot_number']),
            models.Index(fields=['item_sku', '-logged_at']),
            models.Index(fields=['transaction_type', '-logged_at']),
            models.Index(fields=['reference_number', '-logged_at']),
        ]
    
    def __str__(self):
        return f"Lot {self.lot_number} - {self.get_transaction_type_display()} on {self.logged_at.strftime('%Y-%m-%d %H:%M')}"


class LotDepletionLog(models.Model):
    """Logs when a lot is depleted to zero or below"""
    DEPLETION_METHOD_CHOICES = [
        ('production', 'Production Batch'),
        ('sales', 'Sales Order'),
        ('adjustment', 'Inventory Adjustment'),
        ('manual', 'Manual Depletion'),
        ('reversal', 'Reversal/Cancellation'),
    ]
    
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='depletion_logs')
    lot_number = models.CharField(max_length=20, db_index=True, help_text='Snapshot of lot number at time of depletion')
    item_sku = models.CharField(max_length=255, db_index=True, help_text='Item SKU at time of depletion')
    item_name = models.CharField(max_length=255, help_text='Item name at time of depletion')
    vendor = models.CharField(max_length=255, blank=True, null=True, help_text='Vendor at time of depletion')
    
    initial_quantity = models.FloatField(help_text='Original quantity when lot was created')
    quantity_before = models.FloatField(help_text='Quantity remaining before this transaction')
    quantity_used = models.FloatField(help_text='Quantity used in this transaction')
    final_quantity = models.FloatField(help_text='Quantity remaining after this transaction (should be 0 or negative)')
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs', help_text='Unit of measure for quantities')
    
    depletion_method = models.CharField(max_length=20, choices=DEPLETION_METHOD_CHOICES, help_text='How the lot was depleted')
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text='Batch number, SO number, etc.')
    reference_type = models.CharField(max_length=50, blank=True, null=True, help_text='Type of reference (batch_number, so_number, etc.)')
    
    transaction_id = models.IntegerField(blank=True, null=True, help_text='Related InventoryTransaction ID if applicable')
    batch_id = models.IntegerField(blank=True, null=True, help_text='Related ProductionBatch ID if applicable')
    sales_order_id = models.IntegerField(blank=True, null=True, help_text='Related SalesOrder ID if applicable')
    
    notes = models.TextField(blank=True, null=True, help_text='Additional context about the depletion')
    depleted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-depleted_at']
        verbose_name = 'Lot Depletion Log'
        verbose_name_plural = 'Lot Depletion Logs'
        indexes = [
            models.Index(fields=['-depleted_at', 'lot_number']),
            models.Index(fields=['item_sku', '-depleted_at']),
            models.Index(fields=['depletion_method', '-depleted_at']),
        ]
    
    def __str__(self):
        return f"Lot {self.lot_number} depleted via {self.get_depletion_method_display()} on {self.depleted_at.strftime('%Y-%m-%d %H:%M')}"


class PurchaseOrderLog(models.Model):
    """Logs all purchase order activities including creation, updates, and check-ins"""
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('check_in', 'Check-In'),
        ('partial_check_in', 'Partial Check-In'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.CASCADE, related_name='logs')
    po_number = models.CharField(max_length=100, db_index=True, help_text='PO number at time of log')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    
    # Vendor information (snapshot at time of log)
    vendor_name = models.CharField(max_length=255, blank=True, null=True)
    vendor_customer_name = models.CharField(max_length=255, blank=True, null=True)
    
    # PO details (snapshot)
    po_date = models.DateTimeField(blank=True, null=True)
    required_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    carrier = models.CharField(max_length=255, blank=True, null=True)
    po_received_date = models.DateTimeField(blank=True, null=True, help_text='PO received date at time of log')
    
    # Check-in information (if applicable)
    lot_number = models.CharField(max_length=20, blank=True, null=True, help_text='Lot number if this is a check-in')
    item_sku = models.CharField(max_length=255, blank=True, null=True, help_text='Item SKU if this is a check-in')
    item_name = models.CharField(max_length=255, blank=True, null=True, help_text='Item name if this is a check-in')
    quantity_received = models.FloatField(blank=True, null=True, help_text='Quantity received in this check-in')
    received_date = models.DateTimeField(blank=True, null=True, help_text='Date lot was received')
    
    # PO item totals (snapshot)
    total_items = models.IntegerField(default=0, help_text='Total number of items in PO')
    total_quantity_ordered = models.FloatField(default=0.0, help_text='Total quantity ordered')
    total_quantity_received = models.FloatField(default=0.0, help_text='Total quantity received at time of log')
    
    notes = models.TextField(blank=True, null=True, help_text='Additional context')
    logged_at = models.DateTimeField(auto_now_add=True, db_index=True)
    logged_by = models.CharField(max_length=255, blank=True, null=True, help_text='User who performed the action')
    
    class Meta:
        ordering = ['-logged_at']
        verbose_name = 'Purchase Order Log'
        verbose_name_plural = 'Purchase Order Logs'
        indexes = [
            models.Index(fields=['-logged_at', 'po_number']),
            models.Index(fields=['vendor_name', '-logged_at']),
            models.Index(fields=['action', '-logged_at']),
            models.Index(fields=['lot_number', '-logged_at']),
        ]
    
    def __str__(self):
        return f"PO {self.po_number} - {self.get_action_display()} on {self.logged_at.strftime('%Y-%m-%d %H:%M')}"


class CampaignLot(models.Model):
    """
    Customer-facing campaign lot code: ISO year week (YYWW) + product code (e.g. 2609D1307).
    Batch/lot numbers remain the traceability authority; this links batches to a campaign label.
    """
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name='campaign_lots',
    )
    anchor_date = models.DateField(
        help_text='Calendar date used to compute ISO week and YYWW prefix (Mon–Sun ISO week).',
    )
    product_code = models.CharField(
        max_length=40,
        help_text='Product code suffix, e.g. D1307 (pigment, solubility, form, strength).',
    )
    campaign_code = models.CharField(max_length=64, unique=True, db_index=True)
    iso_year = models.PositiveSmallIntegerField()
    iso_week = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Campaign lot'

    def save(self, *args, **kwargs):
        d = self.anchor_date
        if d is not None:
            iso = d.isocalendar()
            self.iso_year = iso[0]
            self.iso_week = iso[1]
            yy = str(iso[0])[-2:]
            ww = f'{iso[1]:02d}'
            pc = (self.product_code or '').strip()
            self.campaign_code = f'{yy}{ww}{pc}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.campaign_code


class ProductionBatch(models.Model):
    BATCH_TYPE_CHOICES = [
        ('production', 'Production'),
        ('repack', 'Repack'),
    ]
    
    batch_number = models.CharField(max_length=100, unique=True, db_index=True)
    batch_type = models.CharField(max_length=20, choices=BATCH_TYPE_CHOICES, default='production')
    finished_good_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='production_batches')
    quantity_produced = models.FloatField()
    quantity_actual = models.FloatField(default=0.0)
    production_date = models.DateTimeField(default=timezone.now)
    closed_date = models.DateTimeField(blank=True, null=True)
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    variance = models.FloatField(default=0.0)
    wastes = models.FloatField(default=0.0)
    spills = models.FloatField(default=0.0)
    notes = models.TextField(blank=True, null=True)
    recipe_snapshot = models.TextField(blank=True, null=True, help_text='JSON: formula overrides used (batch %, substitutions) for audit')
    batch_ticket_mass_unit = models.CharField(
        max_length=16,
        blank=True,
        default='',
        help_text="Default mass unit for batch ticket PDF pick list and batch totals. Empty=native (each line's item UoM). 'lbs' or 'kg' converts all mass quantities.",
    )
    campaign = models.ForeignKey(
        CampaignLot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batches',
        help_text='Optional campaign lot (YYWW+product). Batch lot remains primary for traceability.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Production Batches'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.batch_number


class ProductionBatchInput(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='inputs')
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='production_batch_inputs')
    quantity_used = models.FloatField()
    
    class Meta:
        ordering = ['id']


class ProductionBatchOutput(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='outputs')
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='production_batch_outputs')
    quantity_produced = models.FloatField()
    
    class Meta:
        ordering = ['id']


class ProductionLog(models.Model):
    """Logs all closed production batches with complete information"""
    # Allow null batch reference to preserve log entries even if batch is deleted/reversed
    batch = models.ForeignKey(ProductionBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs')
    batch_number = models.CharField(max_length=100, db_index=True, help_text='Batch number at time of closure')
    batch_type = models.CharField(max_length=20, help_text='production or repack')
    
    # Finished good information
    finished_good_sku = models.CharField(max_length=255, db_index=True)
    finished_good_name = models.CharField(max_length=255)
    
    # Quantities
    quantity_produced = models.FloatField(help_text='Planned quantity')
    quantity_actual = models.FloatField(help_text='Actual quantity produced')
    variance = models.FloatField(default=0.0)
    wastes = models.FloatField(default=0.0)
    spills = models.FloatField(default=0.0)
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs', help_text='Unit of measure for quantities')
    
    # Dates
    production_date = models.DateTimeField(help_text='When batch was produced')
    closed_date = models.DateTimeField(help_text='When batch was closed')
    
    # Input materials (stored as JSON-like text for simplicity)
    input_materials = models.TextField(blank=True, null=True, help_text='JSON string of input materials used')
    input_lots = models.TextField(blank=True, null=True, help_text='JSON string of input lot numbers')
    
    # Output lot information
    output_lot_number = models.CharField(max_length=20, blank=True, null=True)
    output_quantity = models.FloatField(blank=True, null=True)
    
    # Quality control
    qc_parameters = models.TextField(blank=True, null=True)
    qc_actual = models.TextField(blank=True, null=True)
    qc_initials = models.CharField(max_length=255, blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)
    recipe_snapshot = models.TextField(blank=True, null=True, help_text='JSON: batch recipe overrides (%, substitutions) at time of closure')
    closed_by = models.CharField(max_length=255, blank=True, null=True, help_text='User who closed the batch')
    logged_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-logged_at']
        verbose_name = 'Production Log'
        verbose_name_plural = 'Production Logs'
        indexes = [
            models.Index(fields=['-logged_at', 'batch_number']),
            models.Index(fields=['finished_good_sku', '-logged_at']),
            models.Index(fields=['closed_date', '-logged_at']),
        ]
    
    def __str__(self):
        return f"Batch {self.batch_number} closed on {self.closed_date.strftime('%Y-%m-%d %H:%M')}"


class CheckInLog(models.Model):
    """Comprehensive log of all material check-ins with complete form data"""
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, related_name='check_in_logs', null=True, blank=True, help_text='Related lot (null if lot was deleted)')
    lot_number = models.CharField(max_length=100, db_index=True, help_text='Lot number at time of check-in')
    
    # Item information
    item_id = models.IntegerField(blank=True, null=True)
    item_sku = models.CharField(max_length=255, db_index=True)
    item_name = models.CharField(max_length=255)
    item_type = models.CharField(max_length=50, choices=Item.ITEM_TYPE_CHOICES)
    item_unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES)
    
    # Purchase order information
    po_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    vendor_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Check-in form data
    received_date = models.DateTimeField(help_text='Date material was received')
    manufacture_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Manufacturer date when recorded at check-in (snapshot)',
    )
    expiration_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Expiration date for the lot as recorded at check-in (snapshot)',
    )
    vendor_lot_number = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.FloatField(help_text='Quantity received in item native unit')
    quantity_unit = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs', help_text='Unit of measure for quantity')
    status = models.CharField(max_length=20, choices=Lot.STATUS_CHOICES, default='accepted')
    short_reason = models.TextField(blank=True, null=True, help_text='Reason for short quantity if applicable')
    
    # Quality control fields
    coa = models.BooleanField(default=False, help_text='Certificate of Analysis received')
    prod_free_pests = models.BooleanField(default=False, help_text='Product free of pests')
    carrier_free_pests = models.BooleanField(default=False, help_text='Carrier free of pests')
    shipment_accepted = models.BooleanField(default=False, help_text='Shipment accepted')
    initials = models.CharField(max_length=50, blank=True, null=True, help_text='Initials of person who checked in')
    
    # Additional information
    carrier = models.CharField(max_length=255, blank=True, null=True)
    freight_actual = models.FloatField(blank=True, null=True, help_text='Actual freight cost')
    notes = models.TextField(blank=True, null=True, help_text='Additional notes from check-in')
    
    # Metadata
    checked_in_at = models.DateTimeField(auto_now_add=True, db_index=True)
    checked_in_by = models.CharField(max_length=255, blank=True, null=True, help_text='User who performed check-in')
    
    class Meta:
        ordering = ['-checked_in_at']
        verbose_name = 'Check-In Log'
        verbose_name_plural = 'Check-In Logs'
        indexes = [
            models.Index(fields=['-checked_in_at']),
            models.Index(fields=['item_sku', '-checked_in_at']),
            models.Index(fields=['po_number', '-checked_in_at']),
            models.Index(fields=['lot_number', '-checked_in_at']),
        ]
    
    def __str__(self):
        return f"Check-in: {self.item_sku} - {self.quantity} {self.quantity_unit} on {self.checked_in_at.strftime('%Y-%m-%d %H:%M')}"


class LotAttributeChangeLog(models.Model):
    """Audit trail when editable lot fields change after creation (e.g. expiration after re-QC)."""

    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='attribute_change_logs')
    field_name = models.CharField(max_length=64, db_index=True)
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')
    reason = models.CharField(max_length=500, blank=True, default='')
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    changed_by = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Lot attribute change log'
        verbose_name_plural = 'Lot attribute change logs'
        indexes = [
            models.Index(fields=['-changed_at', 'field_name']),
        ]

    def __str__(self):
        return f"Lot {self.lot_id} {self.field_name} @ {self.changed_at}"


class CriticalControlPoint(models.Model):
    """Critical control point (CCP) for pre-production checks on batch tickets (e.g. 20 mesh screen)."""
    name = models.CharField(max_length=255, help_text='e.g. 20 mesh screen, 40 mesh screen')
    display_order = models.PositiveSmallIntegerField(default=0, help_text='Order in dropdowns (lower first)')

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class Formula(models.Model):
    finished_good = models.OneToOneField(
        Item,
        on_delete=models.CASCADE,
        related_name='formula',
        limit_choices_to={'item_type': 'finished_good'}
    )
    version = models.CharField(max_length=50, default='1.0')
    notes = models.TextField(blank=True, null=True)
    critical_control_point = models.ForeignKey(
        CriticalControlPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='formulas',
        help_text='CCP shown on batch ticket pre-production checks (e.g. Has [CCP] been inspected and installed properly?)'
    )

    # Quality Control parameters
    qc_parameter_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text='QC parameter name (e.g., norbixin, betanin, absorbance)'
    )
    qc_spec_min = models.FloatField(
        blank=True, 
        null=True,
        help_text='Minimum acceptable value for QC parameter'
    )
    qc_spec_max = models.FloatField(
        blank=True, 
        null=True,
        help_text='Maximum acceptable value for QC parameter'
    )

    # Mixing steps (Steps 1-6) for batch instructions
    mixing_step_1 = models.TextField(blank=True, null=True, help_text='Mixing step 1')
    mixing_step_2 = models.TextField(blank=True, null=True, help_text='Mixing step 2')
    mixing_step_3 = models.TextField(blank=True, null=True, help_text='Mixing step 3')
    mixing_step_4 = models.TextField(blank=True, null=True, help_text='Mixing step 4')
    mixing_step_5 = models.TextField(blank=True, null=True, help_text='Mixing step 5')
    mixing_step_6 = models.TextField(blank=True, null=True, help_text='Mixing step 6')

    shelf_life_months = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text='Default shelf life in months from batch close / lot receipt; used to set expiration on new FG output lots.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.finished_good.name} - v{self.version}"


class FormulaItem(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name='ingredients')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='formula_ingredients')
    percentage = models.FloatField()
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['id']
        unique_together = [['formula', 'item']]
    
    def __str__(self):
        return f"{self.formula.finished_good.name} - {self.item.name} ({self.percentage}%)"


class RDFormula(models.Model):
    """R&D formula: pre-commercialization BOM for cost estimation; can be promoted to Finished Good."""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('scrapped', 'Scrapped'),
    ]
    name = models.CharField(max_length=255, help_text='Product name (e.g. Natural Red D1307)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'R&D Formula'
        verbose_name_plural = 'R&D Formulas'

    def __str__(self):
        return self.name

    @property
    def total_cost_per_lb(self):
        total = sum(
            (line.formula_cost or 0) for line in self.lines.all()
        )
        return round(total, 2)


class RDFormulaLine(models.Model):
    """Single line in an R&D formula BOM: ingredient, packaging, or labor."""
    LINE_TYPE_CHOICES = [
        ('ingredient', 'Ingredient'),
        ('packaging', 'Packaging'),
        ('labor', 'Labor'),
    ]
    rd_formula = models.ForeignKey(RDFormula, on_delete=models.CASCADE, related_name='lines')
    line_type = models.CharField(max_length=20, choices=LINE_TYPE_CHOICES)
    sequence = models.PositiveSmallIntegerField(default=0, help_text='Order: R1=1, R2=2, P1=3, etc.')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='rd_formula_lines', help_text='Optional: link to Item for dropdown selection')
    description = models.CharField(max_length=255, blank=True, help_text='Display name when no item or override (e.g. Beet Powder 0.8% (Nutracean))')
    composition_pct = models.FloatField(blank=True, null=True, help_text='Composition % (ingredients/packaging); null for labor')
    price_per_lb = models.FloatField(blank=True, null=True, help_text='Price per lb or per unit')
    labor_flat_amount = models.FloatField(blank=True, null=True, help_text='Flat $ for labor line only')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['rd_formula', 'line_type', 'sequence', 'id']
        unique_together = [['rd_formula', 'line_type', 'sequence']]

    def __str__(self):
        return f"{self.rd_formula.name} - {self.get_line_type_display()} #{self.sequence}"

    @property
    def formula_cost(self):
        if self.line_type == 'labor':
            return self.labor_flat_amount
        if self.composition_pct is not None and self.price_per_lb is not None:
            return round((self.composition_pct / 100.0) * self.price_per_lb, 2)
        return None


class PurchaseOrder(models.Model):
    PO_TYPE_CHOICES = [
        ('vendor', 'Vendor'),
        ('customer', 'Customer'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('received', 'Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    po_number = models.CharField(max_length=100, unique=True, db_index=True)
    po_type = models.CharField(max_length=20, choices=PO_TYPE_CHOICES, default='vendor')
    vendor_customer_name = models.CharField(max_length=255)
    vendor_customer_id = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    # Business PO / issue date (editable; staff God mode / historical entry)
    order_date = models.DateTimeField(default=timezone.now)
    order_number = models.CharField(max_length=100, blank=True, null=True, help_text='Internal order number')
    expected_delivery_date = models.DateField(blank=True, null=True)
    required_date = models.DateField(blank=True, null=True)
    received_date = models.DateTimeField(blank=True, null=True)
    shipping_terms = models.CharField(max_length=255, blank=True, null=True)
    shipping_method = models.CharField(max_length=255, blank=True, null=True)
    ship_to_name = models.CharField(max_length=255, default='Wildwood Ingredients, LLC')
    ship_to_address = models.CharField(max_length=255, default='6431 Michels Dr.')
    ship_to_city = models.CharField(max_length=255, default='Washington')
    ship_to_state = models.CharField(max_length=100, default='MO')
    ship_to_zip = models.CharField(max_length=20, default='63090')
    ship_to_country = models.CharField(max_length=100, default='USA')
    vendor_address = models.TextField(blank=True, null=True)
    vendor_city = models.CharField(max_length=255, blank=True, null=True)
    vendor_state = models.CharField(max_length=100, blank=True, null=True)
    vendor_zip = models.CharField(max_length=20, blank=True, null=True)
    vendor_country = models.CharField(max_length=100, blank=True, null=True)
    subtotal = models.FloatField(default=0.0)
    discount = models.FloatField(default=0.0)
    shipping_cost = models.FloatField(default=0.0)
    total = models.FloatField(default=0.0)
    coa_sds_email = models.EmailField(blank=True, null=True, help_text='Email for CoA and SDS')
    tracking_number = models.CharField(max_length=255, blank=True, null=True)
    carrier = models.CharField(max_length=255, blank=True, null=True)
    revision_number = models.IntegerField(default=0)
    original_po = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='revisions')
    notes = models.TextField(blank=True, null=True)
    notify_party_contacts = models.ManyToManyField(
        'VendorContact',
        related_name='purchase_orders_as_notify_party',
        blank=True,
        help_text='Notify party contacts (e.g. customs broker by port) for importation'
    )
    drop_ship = models.BooleanField(
        default=False,
        help_text='Vendor ships direct to final destination; do not check in or mark received into stock.',
    )
    fulfillment_sales_order = models.ForeignKey(
        'SalesOrder',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='drop_ship_purchase_orders',
        help_text='Sales order this drop-ship PO fulfills (ship-to copied from SO).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.po_number

    def calculate_totals(self):
        """Recalculate subtotal from line items and total = subtotal - discount + shipping_cost. Saves the instance."""
        subtotal = sum(
            (item.quantity_ordered * (item.unit_price or 0))
            for item in self.items.all()
        )
        discount = float(self.discount or 0)
        shipping_cost = float(self.shipping_cost or 0)
        self.subtotal = round(subtotal, 2)
        self.total = round(self.subtotal - discount + shipping_cost, 2)
        self.save(update_fields=['subtotal', 'total'])

    def recalculate_totals(self):
        """Alias for calculate_totals for clarity."""
        return self.calculate_totals()


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='purchase_order_items', blank=True, null=True)
    # description field removed - not in database schema
    quantity_ordered = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    unit_price = models.FloatField(blank=True, null=True)
    # unit_cost removed - database only has unit_price, use unit_price instead
    order_uom = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='UoM for quantity_ordered and unit_price on this line (e.g. lbs, kg). Blank means use the item master UoM.',
    )
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['id']


class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('allocated', 'Allocated'),
        ('ready_for_shipment', 'Ready for Shipment'),
        ('issued', 'Issued'),
        ('shipped', 'Shipped'),
        ('received', 'Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    so_number = models.CharField(max_length=100, unique=True, db_index=True)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, blank=True, null=True, related_name='sales_orders', help_text='Customer from customer database')
    ship_to_location = models.ForeignKey('ShipToLocation', on_delete=models.SET_NULL, blank=True, null=True, related_name='sales_orders', help_text='Ship-to location for this order')
    customer_name = models.CharField(max_length=255, help_text='Customer name (legacy field, use customer FK when possible)')
    customer_legacy_id = models.CharField(max_length=100, blank=True, null=True, help_text='Customer ID (legacy field, deprecated - use customer FK)')
    customer_reference_number = models.CharField(max_length=255, blank=True, null=True, help_text='Customer PO number or reference number')
    # Legacy address fields - kept for backward compatibility
    customer_address = models.TextField(blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    customer_city = models.CharField(max_length=100, blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    customer_state = models.CharField(max_length=50, blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    customer_zip = models.CharField(max_length=20, blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    customer_country = models.CharField(max_length=100, blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    customer_phone = models.CharField(max_length=50, blank=True, null=True, help_text='Legacy field - use ship_to_location when possible')
    contact = models.ForeignKey('CustomerContact', on_delete=models.SET_NULL, blank=True, null=True, related_name='sales_orders', help_text='Contact for this order (e.g. billing, sales)')
    # Business order date (editable; staff God mode / historical entry)
    order_date = models.DateTimeField(default=timezone.now)
    expected_ship_date = models.DateTimeField(blank=True, null=True, help_text='Requested ship date')
    actual_ship_date = models.DateTimeField(blank=True, null=True, help_text='Actual ship date')
    carrier = models.CharField(max_length=255, blank=True, null=True, help_text='Shipping carrier (e.g. FedEx, UPS); shown on invoice under SHIPPED VIA')
    tracking_number = models.CharField(max_length=255, blank=True, null=True, help_text='Shipping tracking number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    customer_po_pdf = models.FileField(upload_to='customer_pos/%Y/%m/', blank=True, null=True, help_text='Uploaded customer PO document (PDF)')
    drop_ship = models.BooleanField(
        default=False,
        help_text='Vendor ships direct to customer; do not receive into inventory or allocate from stock.',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.so_number


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='sales_order_items')
    quantity_ordered = models.FloatField()
    quantity_allocated = models.FloatField(default=0.0)
    quantity_shipped = models.FloatField(default=0.0)
    unit_price = models.FloatField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['id']


class LotTraceability(models.Model):
    source_lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='traceability_forward')
    destination_lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='traceability_backward')
    quantity_used = models.FloatField()
    transaction_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Lot Traceabilities'
        ordering = ['-transaction_date']


class Vendor(models.Model):
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]
    
    RISK_PROFILE_CHOICES = [
        ('1', '1 - Low Risk'),
        ('2', '2 - Medium Risk'),
        ('3', '3 - High Risk'),
    ]
    
    RISK_TIER_CHOICES = [
        ('tier_1', 'Tier 1 - Highest Risk'),
        ('tier_2', 'Tier 2 - Standard Risk'),
        ('tier_3', 'Tier 3 - Low Risk'),
    ]
    
    name = models.CharField(max_length=255, unique=True, db_index=True)
    vendor_id = models.CharField(max_length=100, blank=True, null=True)
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True, help_text='Legacy field - use street_address, city, state, country instead')
    street_address = models.CharField(max_length=255, blank=True, null=True, help_text='Street address')
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default='USA')
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='pending')
    risk_profile = models.CharField(max_length=20, choices=RISK_PROFILE_CHOICES, default='2')
    risk_tier = models.CharField(max_length=20, choices=RISK_TIER_CHOICES, blank=True, null=True)
    on_time_performance = models.FloatField(default=100.0)
    quality_complaints = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    payment_terms = models.CharField(max_length=50, blank=True, null=True, help_text='Payment terms (e.g., "Net 30", "Net 60", "Due on Receipt")')
    
    # Service vendor (e.g. customs broker): can have contacts used as notify party on POs
    is_service_vendor = models.BooleanField(default=False, help_text='Service vendor (e.g. customs broker) with contacts for notify party')
    SERVICE_VENDOR_TYPE_CHOICES = [
        ('', '—'),
        ('customs_broker', 'Customs Broker'),
        ('freight_forwarder', 'Freight Forwarder'),
        # To add more: add a tuple here and the same option in frontend SERVICE_VENDOR_TYPE_OPTIONS.
    ]
    service_vendor_type = models.CharField(max_length=50, blank=True, null=True, choices=SERVICE_VENDOR_TYPE_CHOICES, help_text='Type of service vendor')
    
    # Compliance fields
    gfsi_certified = models.BooleanField(default=False)
    gfsi_certificate_number = models.CharField(max_length=255, blank=True, null=True)
    gfsi_certification_body = models.CharField(max_length=255, blank=True, null=True)
    fsma_compliant = models.BooleanField(default=False)
    ctpat_certified = models.BooleanField(default=False)
    bioterrorism_act_registered = models.BooleanField(default=False)
    bioterrorism_number = models.CharField(max_length=100, blank=True, null=True)
    risk_assessment_date = models.DateField(blank=True, null=True)
    risk_assessment_notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class VendorContact(models.Model):
    """Contact at a vendor (sales, logistics, etc.); service vendors also use these for PO notify party."""
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255, help_text='Contact or office name')
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Job title or role (e.g. Sales Manager, Logistics)',
    )
    emails = models.JSONField(
        default=list,
        blank=True,
        help_text='Email addresses (list of strings; multiple allowed)',
    )
    phone = models.CharField(max_length=50, blank=True, null=True)
    location_label = models.CharField(max_length=100, blank=True, null=True, help_text='Port or location (e.g. Long Beach, Houston)')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['vendor', 'location_label', 'name']
        verbose_name = 'Vendor contact'
        verbose_name_plural = 'Vendor contacts'
    
    def __str__(self):
        if self.location_label:
            return f"{self.vendor.name} — {self.name} ({self.location_label})"
        return f"{self.vendor.name} — {self.name}"


class VendorHistory(models.Model):
    HISTORY_TYPE_CHOICES = [
        ('quality_complaint', 'Quality Complaint'),
        ('on_time_issue', 'On-Time Delivery Issue'),
        ('approval_change', 'Approval Status Change'),
        ('risk_change', 'Risk Profile Change'),
        ('other', 'Other'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='history')
    history_type = models.CharField(max_length=50, choices=HISTORY_TYPE_CHOICES)
    description = models.TextField()
    date = models.DateTimeField(default=timezone.now)
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Vendor Histories'
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.vendor.name} - {self.history_type}"


class SupplierSurvey(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]
    
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='survey')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    submitted_date = models.DateTimeField(blank=True, null=True)
    reviewed_date = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.CharField(max_length=100, blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    company_info = models.JSONField(default=dict, blank=True)
    compliance_responses = models.JSONField(default=dict, blank=True)
    quality_program_responses = models.JSONField(default=dict, blank=True)
    food_security_responses = models.JSONField(default=dict, blank=True)
    see_program_responses = models.JSONField(default=dict, blank=True)
    reviewer_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.vendor.name} - Survey"


class SupplierDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('certificate_of_insurance', 'Certificate of Insurance'),
        ('letter_of_guarantee', 'Letter of Guarantee'),
        ('third_party_audit', 'Third-Party Audit Certificate'),
        ('recall_plan', 'Recall and Traceability Plan'),
        ('traceability_program', 'Traceability Program'),
        ('code_of_conduct', 'Code of Conduct'),
        ('gfsi_certificate', 'GFSI Certificate'),
        ('fsma_statement', 'FSMA Statement'),
        ('haccp_plan', 'HACCP Plan'),
        ('food_defense_statement', 'Food Defense Statement'),
        ('spec_sheet', 'Spec Sheet'),
        ('sds', 'Safety Data Sheet (SDS)'),
        ('nutritional_info', 'Nutritional Information'),
        ('allergen_statement', 'Allergen Statement'),
        ('halal_certificate', 'Halal Certificate'),
        ('kosher_certificate', 'Kosher Certificate'),
        ('other', 'Other'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    document_name = models.CharField(max_length=255)
    file = models.BinaryField(blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.IntegerField(blank=True, null=True)
    mime_type = models.CharField(max_length=100, default='application/pdf')
    issue_date = models.DateField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    uploaded_by = models.CharField(max_length=100, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['vendor', 'document_type']),
            models.Index(fields=['expiration_date']),
        ]
    
    def __str__(self):
        return f"{self.vendor.name} - {self.document_name}"


class CostMaster(models.Model):
    INCOTERMS_CHOICES = [
        ('CIF', 'CIF'),
        ('FCA', 'FCA'),
        ('EXW', 'EXW'),
        ('CIP', 'CIP'),
        ('FOB', 'FOB'),
        ('DDP', 'DDP'),
        ('DAP', 'DAP'),
    ]
    
    vendor_material = models.CharField(max_length=255, db_index=True)
    wwi_product_code = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    price_per_kg = models.FloatField(blank=True, null=True)
    price_per_lb = models.FloatField(blank=True, null=True)
    incoterms = models.CharField(max_length=50, choices=INCOTERMS_CHOICES, blank=True, null=True)
    incoterms_place = models.CharField(
        max_length=255, blank=True, null=True,
        help_text='Named place for the Incoterm (e.g. "Long Beach, CA" for FCA Long Beach, CA). Origin remains country of origin.'
    )
    origin = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    hts_code = models.CharField(max_length=50, blank=True, null=True)
    tariff = models.FloatField(default=0.0)
    freight_per_kg = models.FloatField(default=0.0, help_text='Freight estimate per kg')
    cert_cost_per_kg = models.FloatField(default=0.0)
    landed_cost_per_kg = models.FloatField(blank=True, null=True)
    landed_cost_per_lb = models.FloatField(blank=True, null=True)
    margin = models.FloatField(blank=True, null=True)
    selling_price_per_kg = models.FloatField(blank=True, null=True)
    selling_price_per_lb = models.FloatField(blank=True, null=True)
    strength = models.CharField(max_length=255, blank=True, null=True)
    minimum = models.CharField(max_length=255, blank=True, null=True)
    lead_time = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['vendor_material', 'wwi_product_code']
        indexes = [
            models.Index(fields=['wwi_product_code']),
            models.Index(fields=['vendor']),
            models.Index(fields=['vendor_material']),
        ]
    
    def calculate_landed_cost(self):
        """Calculate landed cost based on Excel formula: (Price per kg * (1 + Tariff)) + Freight per kg"""
        if self.price_per_kg is not None:
            # Formula: (Price per kg * (1 + Tariff)) + Freight per kg
            self.landed_cost_per_kg = (self.price_per_kg * (1 + (self.tariff or 0))) + (self.freight_per_kg or 0)
            # Convert to lb
            self.landed_cost_per_lb = self.landed_cost_per_kg / 2.20462
        elif self.price_per_lb is not None:
            # If only price_per_lb is available, convert to kg first
            price_per_kg = self.price_per_lb * 2.20462
            self.landed_cost_per_kg = (price_per_kg * (1 + (self.tariff or 0))) + (self.freight_per_kg or 0)
            self.landed_cost_per_lb = self.landed_cost_per_kg / 2.20462
        else:
            self.landed_cost_per_kg = None
            self.landed_cost_per_lb = None
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate landed cost"""
        self.calculate_landed_cost()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.vendor_material} - {self.wwi_product_code or 'N/A'}"


class CostMasterHistory(models.Model):
    """Track historical pricing changes for CostMaster items"""
    cost_master = models.ForeignKey(CostMaster, on_delete=models.CASCADE, related_name='price_history')
    price_per_kg = models.FloatField(blank=True, null=True)
    price_per_lb = models.FloatField(blank=True, null=True)
    effective_date = models.DateTimeField(auto_now_add=True)
    changed_by = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text='Reason for price change')
    
    class Meta:
        ordering = ['-effective_date']
        indexes = [
            models.Index(fields=['cost_master', '-effective_date']),
        ]
    
    def __str__(self):
        return f"{self.cost_master.vendor_material} - {self.effective_date.strftime('%Y-%m-%d')}"


class Account(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
    ]
    
    account_number = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=50, choices=ACCOUNT_TYPE_CHOICES)
    parent_account = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='sub_accounts')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['account_number']
    
    def __str__(self):
        return f"{self.account_number} - {self.name}"


class TemporaryException(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='exceptions')
    material_commodity = models.CharField(max_length=255)
    country_of_origin = models.CharField(max_length=255, blank=True, null=True)
    intended_use = models.TextField()
    po_number = models.CharField(max_length=100, blank=True, null=True)
    lot_number = models.CharField(max_length=100, blank=True, null=True)
    justification = models.TextField()
    risk_summary = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.CharField(max_length=100)
    requested_date = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-requested_date']
    
    def __str__(self):
        return f"{self.vendor.name} - {self.material_commodity}"


class Customer(models.Model):
    """Customer information for sales orders"""
    customer_id = models.CharField(max_length=100, unique=True, db_index=True, help_text='Unique customer identifier')
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True, help_text='Headquarters street address')
    city = models.CharField(max_length=100, blank=True, null=True, help_text='Headquarters city')
    state = models.CharField(max_length=50, blank=True, null=True, help_text='Headquarters state')
    zip_code = models.CharField(max_length=20, blank=True, null=True, help_text='Headquarters ZIP')
    country = models.CharField(max_length=100, blank=True, null=True, default='USA', help_text='Headquarters country')
    bill_to_address = models.TextField(blank=True, null=True, help_text='Bill-to street address (leave blank if same as HQ)')
    bill_to_city = models.CharField(max_length=100, blank=True, null=True)
    bill_to_state = models.CharField(max_length=50, blank=True, null=True)
    bill_to_zip_code = models.CharField(max_length=20, blank=True, null=True)
    bill_to_country = models.CharField(max_length=100, blank=True, null=True)
    payment_terms = models.CharField(max_length=50, blank=True, null=True, help_text='Payment terms (e.g., "Net 30", "Net 15", "Due on Receipt")')
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.customer_id} - {self.name}"


class ShipToLocation(models.Model):
    """Ship-to locations for customers"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='ship_to_locations')
    location_name = models.CharField(max_length=255, help_text='Name/identifier for this location (e.g., "Main Warehouse", "West Coast Facility")')
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='USA')
    is_default = models.BooleanField(default=False, help_text='Default ship-to location for this customer')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', 'location_name']
        verbose_name_plural = 'Ship-to Locations'
    
    def __str__(self):
        return f"{self.customer.name} - {self.location_name}"


class CustomerContact(models.Model):
    """Contacts associated with customers"""
    CONTACT_TYPE_CHOICES = [
        ('billing', 'Billing'),
        ('sales', 'Sales'),
        ('shipping', 'Shipping'),
        ('general', 'General'),
        ('other', 'Other'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='contacts')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    title = models.CharField(max_length=100, blank=True, null=True, help_text='Job title/position')
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPE_CHOICES, default='general', help_text='Type of contact (e.g. Billing, Sales)')
    emails = models.JSONField(
        default=list,
        blank=True,
        help_text='Email addresses (list of strings; multiple allowed)',
    )
    phone = models.CharField(max_length=50, blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    is_primary = models.BooleanField(default=False, help_text='Primary contact for this customer')
    is_ap_contact = models.BooleanField(default=False, help_text='A/P contact: receives invoices when issued')
    is_purchasing_contact = models.BooleanField(default=False, help_text='Purchasing contact: receives sales order confirmations when issued')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_primary', 'last_name', 'first_name']
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def __str__(self):
        return f"{self.customer.name} - {self.full_name}"


class SalesCall(models.Model):
    """Sales call history/log"""
    CALL_TYPE_CHOICES = [
        ('phone', 'Phone Call'),
        ('email', 'Email'),
        ('meeting', 'In-Person Meeting'),
        ('video', 'Video Call'),
        ('other', 'Other'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='sales_calls')
    contact = models.ForeignKey(CustomerContact, on_delete=models.SET_NULL, blank=True, null=True, related_name='sales_calls')
    call_date = models.DateTimeField(default=timezone.now)
    call_type = models.CharField(max_length=20, choices=CALL_TYPE_CHOICES, default='phone')
    subject = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(help_text='Call notes, discussion points, outcomes')
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True, help_text='User who logged the call')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-call_date']
    
    def __str__(self):
        return f"{self.customer.name} - {self.call_date.strftime('%Y-%m-%d %H:%M')}"


class CustomerForecast(models.Model):
    """Customer forecasting data"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='forecasts')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='customer_forecasts')
    forecast_period = models.CharField(max_length=20, help_text='Period identifier (e.g., "2025-Q1", "2025-01")')
    forecast_quantity = models.FloatField(help_text='Forecasted quantity')
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs')
    notes = models.TextField(blank=True, null=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-forecast_period', 'item__sku']
        unique_together = [['customer', 'item', 'forecast_period']]
    
    def __str__(self):
        return f"{self.customer.name} - {self.item.sku} - {self.forecast_period}"


class CustomerPricing(models.Model):
    """Customer-specific pricing for items"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='pricing')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='customer_pricing')
    unit_price = models.FloatField()
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs')
    incoterms = models.CharField(max_length=30, blank=True, null=True, help_text='Incoterms for this item (e.g. FOB, CIF, DAP)')
    incoterms_place = models.CharField(max_length=100, blank=True, null=True, help_text='Place/point for the incoterm (e.g. New York for CIF New York)')
    effective_date = models.DateField()
    expiry_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['customer', 'item', '-effective_date']
        unique_together = [['customer', 'item', 'effective_date']]
        indexes = [
            models.Index(fields=['customer', 'item', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.customer.name} - {self.item.sku} - ${self.unit_price}/{self.unit_of_measure}"


class VendorPricing(models.Model):
    """Vendor-specific pricing for items"""
    vendor_name = models.CharField(max_length=255, db_index=True)
    vendor_item_number = models.CharField(max_length=255, blank=True, null=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='vendor_pricing')
    unit_price = models.FloatField()
    unit_of_measure = models.CharField(max_length=10, choices=Item.UNIT_CHOICES, default='lbs')
    effective_date = models.DateField()
    expiry_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['vendor_name', 'item', '-effective_date']
        unique_together = [['vendor_name', 'item', 'effective_date']]
        indexes = [
            models.Index(fields=['vendor_name', 'item', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.vendor_name} - {self.item.sku} - ${self.unit_price}/{self.unit_of_measure}"


class SalesOrderLot(models.Model):
    """Link lots to sales order items for allocation"""
    sales_order_item = models.ForeignKey(SalesOrderItem, on_delete=models.CASCADE, related_name='allocated_lots')
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='sales_order_allocations')
    quantity_allocated = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['sales_order_item', 'lot']
        unique_together = [['sales_order_item', 'lot']]
    
    def __str__(self):
        return f"{self.sales_order_item.sales_order.so_number} - {self.lot.lot_number} - {self.quantity_allocated}"


class ShipIdempotency(models.Model):
    """
    Stores successful /sales-orders/{id}/ship/ responses keyed by X-Idempotency-Key
    so duplicate submits (double-click, retries) cannot create duplicate shipments.
    """
    key = models.CharField(max_length=128, unique=True, db_index=True)
    sales_order = models.ForeignKey('SalesOrder', on_delete=models.CASCADE, related_name='ship_idempotencies')
    shipment = models.ForeignKey('Shipment', on_delete=models.CASCADE, related_name='idempotency_records')
    response_json = models.TextField(help_text='JSON body returned to the client')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Ship idempotency keys'

    def __str__(self):
        return f'{self.key[:16]}… → shipment {self.shipment_id}'


class Shipment(models.Model):
    """Track individual shipments for sales orders (supports multiple shipments per order)."""
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='shipments')
    expected_ship_date = models.DateTimeField(
        blank=True, null=True,
        help_text='Agreed/due date for this release. Used for on-time KPI (compare to ship_date).'
    )
    ship_date = models.DateTimeField(help_text='Date the shipment was shipped')
    tracking_number = models.CharField(max_length=255, help_text='Tracking number for this shipment')
    notes = models.TextField(blank=True, null=True)
    dimensions = models.TextField(blank=True, null=True, help_text='Human-readable summary; per-piece values in piece_dimensions')
    pieces = models.PositiveIntegerField(blank=True, null=True, help_text='Number of boxes (ground) or pallets (FTL/LTL)')
    piece_dimensions = models.JSONField(
        blank=True,
        null=True,
        help_text='List of dimension strings, one per handling unit (same length as pieces)',
    )
    piece_weights = models.JSONField(
        blank=True,
        null=True,
        help_text='List of weight strings per handling unit (same length as pieces), e.g. "45 lbs"',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-ship_date', '-created_at']
    
    def __str__(self):
        return f"{self.sales_order.so_number} - {self.ship_date.strftime('%Y-%m-%d')} - {self.tracking_number}"


class ShipmentItem(models.Model):
    """Items shipped in a specific shipment"""
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items')
    sales_order_item = models.ForeignKey(SalesOrderItem, on_delete=models.CASCADE, related_name='shipment_items')
    quantity_shipped = models.FloatField(help_text='Quantity shipped in this specific shipment')
    
    class Meta:
        ordering = ['shipment', 'sales_order_item']
    
    def __str__(self):
        return f"{self.shipment.sales_order.so_number} - {self.sales_order_item.item.name} - {self.quantity_shipped}"


class Invoice(models.Model):
    """Invoice for sales orders"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    INVOICE_TYPE_CHOICES = [
        ('customer', 'Customer Invoice'),
        ('vendor', 'Vendor Bill'),
    ]
    
    invoice_number = models.CharField(max_length=100, unique=True, db_index=True)
    invoice_type = models.CharField(max_length=20, choices=INVOICE_TYPE_CHOICES, default='customer')
    customer_vendor_name = models.CharField(max_length=255, blank=True, default='')
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='invoices', blank=True, null=True, db_column='sales_order_id')
    contact = models.ForeignKey(CustomerContact, on_delete=models.SET_NULL, blank=True, null=True, related_name='invoices', help_text='Bill-to or primary contact for this invoice')
    invoice_date = models.DateField()
    due_date = models.DateField(help_text='Calculated from invoice_date + payment_terms')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.FloatField(default=0.0)
    freight = models.FloatField(default=0.0)
    tax = models.FloatField(default=0.0)
    tax_amount = models.FloatField(default=0.0)  # DB column from migrations; same as tax for customer invoices
    discount = models.FloatField(default=0.0)
    grand_total = models.FloatField(default=0.0)
    total_amount = models.FloatField(default=0.0)  # DB column from migrations; same as grand_total
    paid_amount = models.FloatField(default=0.0)  # DB column from migrations
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-invoice_date', '-created_at']
    
    def __str__(self):
        if self.sales_order:
            return f"{self.invoice_number} - {self.sales_order.so_number}"
        return f"{self.invoice_number}"

    def _payment_terms_string_for_due_date(self):
        """Customer payment terms from linked sales order or bill-to contact."""
        if self.sales_order_id:
            try:
                so = self.sales_order
                if so is None:
                    so = SalesOrder.objects.filter(pk=self.sales_order_id).select_related('customer').first()
                if so and getattr(so, 'customer', None):
                    return (so.customer.payment_terms or '').strip()
            except Exception:
                pass
        if self.contact_id:
            try:
                cc = self.contact
                if cc is None:
                    cc = CustomerContact.objects.filter(pk=self.contact_id).select_related('customer').first()
                if cc and getattr(cc, 'customer', None):
                    return (cc.customer.payment_terms or '').strip()
            except Exception:
                pass
        return ''

    def save(self, *args, **kwargs):
        from .invoice_helpers import due_date_from_issue_and_payment_terms
        if self.invoice_date:
            terms = self._payment_terms_string_for_due_date()
            self.due_date = due_date_from_issue_and_payment_terms(self.invoice_date, terms)
        super().save(*args, **kwargs)
    
    @property
    def days_aging(self):
        """Calculate days aging (overdue) from due date. Only counts after invoice is Issued (sent)."""
        from django.utils import timezone
        if self.status == 'paid':
            return 0
        if self.status == 'draft':
            return 0  # Don't start aging until invoice is moved to Issued
        if not self.due_date:
            return 0
        today = timezone.now().date()
        return (today - self.due_date).days


class InvoiceItem(models.Model):
    """Line items for invoices."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('Item', on_delete=models.SET_NULL, related_name='invoice_items', blank=True, null=True)
    sales_order_item = models.ForeignKey(
        SalesOrderItem, on_delete=models.CASCADE, related_name='invoice_items', blank=True, null=True
    )
    description = models.CharField(max_length=255)
    quantity = models.FloatField()
    unit_price = models.FloatField()
    total = models.FloatField()
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description}"


class FiscalPeriod(models.Model):
    """Fiscal periods for accounting (monthly, quarterly, etc.)"""
    period_name = models.CharField(max_length=50, unique=True, help_text='e.g., "2024-01" for January 2024')
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False, help_text='Whether this period has been closed')
    closed_date = models.DateTimeField(blank=True, null=True)
    closed_by = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_closed']),
        ]
    
    def __str__(self):
        return f"{self.period_name} ({'Closed' if self.is_closed else 'Open'})"


class JournalEntry(models.Model):
    """Journal entries for double-entry bookkeeping"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
    ]
    
    entry_number = models.CharField(max_length=100, unique=True, db_index=True, help_text='Auto-generated journal entry number')
    entry_date = models.DateField(db_index=True)
    description = models.TextField()
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text='Reference to source document (PO, SO, Invoice, etc.)')
    reference_type = models.CharField(max_length=50, blank=True, null=True, help_text='Type of reference (invoice, purchase_order, sales_order, manual, etc.)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    fiscal_period = models.ForeignKey(FiscalPeriod, on_delete=models.SET_NULL, blank=True, null=True, related_name='journal_entries')
    created_by = models.CharField(max_length=100, blank=True, null=True)
    posted_by = models.CharField(max_length=100, blank=True, null=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Journal Entries'
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['entry_date', 'status']),
            models.Index(fields=['reference_number', 'reference_type']),
            models.Index(fields=['fiscal_period', 'entry_date']),
        ]
    
    def __str__(self):
        return f"{self.entry_number} - {self.description[:50]}"
    
    def validate_balanced(self):
        """Validate that debits equal credits"""
        total_debits = sum(line.amount for line in self.lines.filter(debit_credit='debit'))
        total_credits = sum(line.amount for line in self.lines.filter(debit_credit='credit'))
        return abs(total_debits - total_credits) < 0.01


class JournalEntryLine(models.Model):
    """Individual lines within a journal entry"""
    DEBIT_CREDIT_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]
    
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='journal_lines')
    debit_credit = models.CharField(max_length=10, choices=DEBIT_CREDIT_CHOICES)
    amount = models.FloatField()
    description = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['account', 'journal_entry']),
            models.Index(fields=['journal_entry', 'debit_credit']),
        ]
    
    def __str__(self):
        return f"{self.journal_entry.entry_number} - {self.account.account_number} - {self.debit_credit} ${self.amount}"


class GeneralLedgerEntry(models.Model):
    """General ledger entries (posted journal entry lines)"""
    entry_date = models.DateField(db_index=True)
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='ledger_entries')
    journal_entry_line = models.ForeignKey(JournalEntryLine, on_delete=models.CASCADE, related_name='ledger_entry')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='ledger_entries')
    debit_credit = models.CharField(max_length=10, choices=JournalEntryLine.DEBIT_CREDIT_CHOICES)
    amount = models.FloatField()
    description = models.CharField(max_length=255, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    fiscal_period = models.ForeignKey(FiscalPeriod, on_delete=models.SET_NULL, blank=True, null=True, related_name='ledger_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'General Ledger Entries'
        ordering = ['entry_date', 'id']
        indexes = [
            models.Index(fields=['account', 'entry_date']),
            models.Index(fields=['entry_date', 'fiscal_period']),
            models.Index(fields=['journal_entry', 'account']),
        ]
    
    def __str__(self):
        return f"{self.entry_date} - {self.account.account_number} - {self.debit_credit} ${self.amount}"


class AccountBalance(models.Model):
    """Account balances by fiscal period (for faster reporting)"""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='balances')
    fiscal_period = models.ForeignKey(FiscalPeriod, on_delete=models.CASCADE, related_name='account_balances')
    opening_balance = models.FloatField(default=0.0, help_text='Opening balance at start of period')
    period_debits = models.FloatField(default=0.0)
    period_credits = models.FloatField(default=0.0)
    closing_balance = models.FloatField(default=0.0, help_text='Closing balance at end of period')
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['account', 'fiscal_period']]
        ordering = ['account', 'fiscal_period']
        indexes = [
            models.Index(fields=['account', 'fiscal_period']),
            models.Index(fields=['fiscal_period', 'account']),
        ]
    
    def __str__(self):
        return f"{self.account.account_number} - {self.fiscal_period.period_name} - Balance: ${self.closing_balance}"


class AccountsPayable(models.Model):
    """Accounts Payable - tracks amounts owed to vendors"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    vendor_name = models.CharField(max_length=255, db_index=True, help_text='Vendor name')
    vendor_id = models.CharField(max_length=100, blank=True, null=True, help_text='Vendor ID if available')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, blank=True, null=True, related_name='ap_entries', help_text='Related purchase order')
    invoice_number = models.CharField(max_length=100, blank=True, null=True, help_text='Vendor invoice number')
    invoice_date = models.DateField(help_text='Date of vendor invoice')
    due_date = models.DateField(help_text='Payment due date')
    original_amount = models.FloatField(help_text='Original invoice amount')
    amount_paid = models.FloatField(default=0.0, help_text='Amount paid so far')
    balance = models.FloatField(help_text='Outstanding balance (original_amount - amount_paid)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='ap_entries', help_text='AP account')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, blank=True, null=True, related_name='ap_entries', help_text='Journal entry created for this AP')
    notes = models.TextField(blank=True, null=True)
    COST_CATEGORY_CHOICES = [
        ('', 'Legacy / unspecified'),
        ('material', 'Material — vendor goods invoice (COGS)'),
        ('freight', 'Freight — shipping / logistics invoice'),
        ('duty_tax', 'Duty & tax — CBP, customs, broker'),
    ]
    cost_category = models.CharField(
        max_length=20,
        choices=COST_CATEGORY_CHOICES,
        blank=True,
        default='',
        help_text='For landed cost: classify this AP line (link same PO on vendor, freight, and duty invoices).',
    )
    # Actual cost tracking (from vendor invoice / import) — used for cost actuals vs Cost Master estimates
    freight_total = models.FloatField(blank=True, null=True, help_text='Actual total freight on this invoice/shipment (spread over quantity for unit cost)')
    tariff_duties_paid = models.FloatField(blank=True, null=True, help_text='Duties/tariff paid at import for this shipment')
    shipment_method = models.CharField(
        max_length=20, blank=True, null=True,
        choices=[('air', 'Air'), ('sea', 'Sea')],
        help_text='Method of shipment (air vs sea)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Accounts Payable'
        ordering = ['due_date', 'vendor_name']
        indexes = [
            models.Index(fields=['vendor_name', 'status']),
            models.Index(fields=['due_date', 'status']),
            models.Index(fields=['purchase_order', 'status']),
        ]
    
    def __str__(self):
        return f"AP - {self.vendor_name} - ${self.balance} (Due: {self.due_date})"
    
    @property
    def days_aging(self):
        """Calculate days aging (overdue) from due date"""
        from django.utils import timezone
        if self.status == 'paid':
            return 0
        today = timezone.now().date()
        return (today - self.due_date).days
    
    @property
    def aging_bucket(self):
        """Categorize into aging buckets"""
        days = self.days_aging
        if days < 0:
            return 'not_due'
        elif days <= 30:
            return '0-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        else:
            return 'over_90'


class AccountsReceivable(models.Model):
    """Accounts Receivable - tracks amounts owed by customers"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    customer_name = models.CharField(max_length=255, db_index=True, help_text='Customer name')
    customer_id = models.CharField(max_length=100, blank=True, null=True, help_text='Customer ID if available')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='ar_entries', help_text='Related invoice')
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.SET_NULL, blank=True, null=True, related_name='ar_entries', help_text='Related sales order')
    invoice_date = models.DateField(help_text='Date of invoice')
    due_date = models.DateField(help_text='Payment due date')
    original_amount = models.FloatField(help_text='Original invoice amount')
    amount_paid = models.FloatField(default=0.0, help_text='Amount paid so far')
    balance = models.FloatField(help_text='Outstanding balance (original_amount - amount_paid)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='ar_entries', help_text='AR account')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, blank=True, null=True, related_name='ar_entries', help_text='Journal entry created for this AR')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Accounts Receivable'
        ordering = ['due_date', 'customer_name']
        indexes = [
            models.Index(fields=['customer_name', 'status']),
            models.Index(fields=['due_date', 'status']),
            models.Index(fields=['invoice', 'status']),
        ]
    
    def __str__(self):
        return f"AR - {self.customer_name} - ${self.balance} (Due: {self.due_date})"
    
    @property
    def days_aging(self):
        """Calculate days aging (overdue) from due date"""
        from django.utils import timezone
        if self.status == 'paid':
            return 0
        today = timezone.now().date()
        return (today - self.due_date).days
    
    @property
    def aging_bucket(self):
        """Categorize into aging buckets"""
        days = self.days_aging
        if days < 0:
            return 'not_due'
        elif days <= 30:
            return '0-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        else:
            return 'over_90'


class Payment(models.Model):
    """Payments made (for AP) or received (for AR)"""
    PAYMENT_TYPE_CHOICES = [
        ('ap_payment', 'Accounts Payable Payment'),
        ('ar_payment', 'Accounts Receivable Payment'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('check', 'Check'),
        ('wire', 'Wire Transfer'),
        ('ach', 'ACH'),
        ('credit_card', 'Credit Card'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ]
    
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.FloatField()
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text='Check number, wire reference, etc.')
    ap_entry = models.ForeignKey(AccountsPayable, on_delete=models.CASCADE, blank=True, null=True, related_name='payments', help_text='AP entry being paid')
    ar_entry = models.ForeignKey(AccountsReceivable, on_delete=models.CASCADE, blank=True, null=True, related_name='payments', help_text='AR entry being paid')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='payments', help_text='Cash/bank account used for payment')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, blank=True, null=True, related_name='payments', help_text='Journal entry created for this payment')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_type', 'payment_date']),
            models.Index(fields=['ap_entry', 'payment_date']),
            models.Index(fields=['ar_entry', 'payment_date']),
        ]
    
    def __str__(self):
        if self.ap_entry:
            return f"AP Payment - {self.ap_entry.vendor_name} - ${self.amount}"
        elif self.ar_entry:
            return f"AR Payment - {self.ar_entry.customer_name} - ${self.amount}"
        return f"Payment - ${self.amount}"


class BankReconciliation(models.Model):
    """Bank account reconciliation: statement date and balance for comparison to GL."""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='bank_reconciliations')
    statement_date = models.DateField(help_text='Bank statement date')
    statement_balance = models.FloatField(help_text='Ending balance per bank statement')
    reconciled_at = models.DateTimeField(blank=True, null=True, help_text='When reconciliation was completed')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-statement_date']
        verbose_name_plural = 'Bank Reconciliations'
        indexes = [models.Index(fields=['account', 'statement_date'])]

    def __str__(self):
        return f"{self.account.account_number} - {self.statement_date} - ${self.statement_balance}"


class OrphanedInventory(models.Model):
    """Stores orphaned lots when an item is deleted but has inventory"""
    original_item_sku = models.CharField(max_length=255, db_index=True, help_text='SKU of the deleted item')
    original_item_name = models.CharField(max_length=255, help_text='Name of the deleted item')
    original_item_vendor = models.CharField(max_length=255, blank=True, null=True, help_text='Vendor of the deleted item')
    original_item_type = models.CharField(max_length=50, help_text='Item type of the deleted item')
    original_item_unit = models.CharField(max_length=10, help_text='Unit of measure of the deleted item')
    
    lot_number = models.CharField(max_length=20, unique=True, db_index=True, help_text='Lot number that was orphaned')
    vendor_lot_number = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.FloatField(help_text='Total quantity in the lot')
    quantity_remaining = models.FloatField(help_text='Quantity remaining in the lot')
    received_date = models.DateTimeField(help_text='Original received date')
    expiration_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='accepted')
    po_number = models.CharField(max_length=100, blank=True, null=True)
    freight_actual = models.FloatField(blank=True, null=True)
    short_reason = models.CharField(max_length=255, blank=True, null=True)
    
    # Link to new item if reassigned
    reassigned_item = models.ForeignKey('Item', on_delete=models.SET_NULL, blank=True, null=True, related_name='reassigned_orphaned_inventory', help_text='Item this orphaned inventory was reassigned to')
    reassigned_at = models.DateTimeField(blank=True, null=True, help_text='When this inventory was reassigned')
    reassigned_by = models.CharField(max_length=255, blank=True, null=True, help_text='Who reassigned this inventory')
    
    created_at = models.DateTimeField(auto_now_add=True, help_text='When the item was deleted and inventory orphaned')
    notes = models.TextField(blank=True, null=True, help_text='Additional notes about the orphaned inventory')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Orphaned Inventory'
    
    def __str__(self):
        return f"Orphaned: {self.lot_number} ({self.original_item_sku})"


class OrphanedPurchaseOrderItem(models.Model):
    """Stores orphaned purchase order items when an item is deleted"""
    original_item_sku = models.CharField(max_length=255, db_index=True, help_text='SKU of the deleted item')
    original_item_name = models.CharField(max_length=255, help_text='Name of the deleted item')
    original_item_vendor = models.CharField(max_length=255, blank=True, null=True)
    original_item_unit = models.CharField(max_length=10, help_text='Unit of measure of the deleted item')
    
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.CASCADE, related_name='orphaned_items', help_text='Purchase order this item belongs to')
    quantity_ordered = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    unit_price = models.FloatField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Link to new item if reassigned
    reassigned_item = models.ForeignKey('Item', on_delete=models.SET_NULL, blank=True, null=True, related_name='reassigned_orphaned_po_items', help_text='Item this orphaned PO item was reassigned to')
    reassigned_at = models.DateTimeField(blank=True, null=True)
    reassigned_by = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True, help_text='When the item was deleted and PO item orphaned')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Orphaned Purchase Order Items'
    
    def __str__(self):
        return f"Orphaned PO Item: {self.original_item_sku} (PO: {self.purchase_order.po_number})"


class UserProfile(models.Model):
    """Extended profile for ERP users: role (license tier) for access control."""
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('operator', 'Operator'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='erp_profile',
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='viewer',
        help_text='Access tier: Viewer (read-only), Operator, Manager, Admin (full).',
    )

    class Meta:
        db_table = 'erp_core_userprofile'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

