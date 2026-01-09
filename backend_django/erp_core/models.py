from django.db import models
from django.utils import timezone


class Item(models.Model):
    ITEM_TYPE_CHOICES = [
        ('raw_material', 'Raw Material'),
        ('distributed_item', 'Distributed Item'),
        ('finished_good', 'Finished Good'),
        ('indirect_material', 'Indirect Material'),
    ]
    
    UNIT_CHOICES = [
        ('lbs', 'Pounds'),
        ('kg', 'Kilograms'),
        ('ea', 'Each'),
    ]
    
    sku = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    item_type = models.CharField(max_length=50, choices=ITEM_TYPE_CHOICES)
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES)
    vendor = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    pack_size = models.FloatField(blank=True, null=True, help_text='Pack size in the unit of measure')
    price = models.FloatField(blank=True, null=True, help_text='Price per unit of measure')
    on_order = models.FloatField(default=0.0, help_text='Quantity currently on order')
    approved_for_formulas = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sku', 'vendor']
        unique_together = [['sku', 'vendor']]
    
    def __str__(self):
        return f"{self.sku} - {self.name}"


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
    """Sequence tracking for PO numbers (format: 2yy0000)"""
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


class Lot(models.Model):
    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('on_hold', 'On Hold'),
    ]
    
    lot_number = models.CharField(max_length=20, unique=True, db_index=True)
    vendor_lot_number = models.CharField(max_length=100, blank=True, null=True, help_text='Vendor lot number from check-in form')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='lots')
    quantity = models.FloatField()
    quantity_remaining = models.FloatField()
    received_date = models.DateTimeField()
    expiration_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='accepted', help_text='Acceptance status of the lot')
    on_hold = models.BooleanField(default=False, help_text='Lot is on hold and not available for use (deprecated - use status instead)')
    freight_actual = models.FloatField(blank=True, null=True, help_text='Actual freight cost for this lot')
    po_number = models.CharField(max_length=100, blank=True, null=True, help_text='Purchase order number associated with this lot')
    short_reason = models.CharField(max_length=255, blank=True, null=True, help_text='Reason for short shipment (damage, short shipped, etc.)')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.lot_number


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('receipt', 'Receipt'),
        ('sale', 'Sale'),
        ('adjustment', 'Adjustment'),
        ('production', 'Production'),
    ]
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name='inventory_transactions')
    quantity = models.FloatField()
    transaction_date = models.DateTimeField(auto_now_add=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-transaction_date']


class ProductionBatch(models.Model):
    batch_number = models.CharField(max_length=100, unique=True, db_index=True)
    finished_good_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='production_batches')
    quantity_produced = models.FloatField()
    quantity_actual = models.FloatField(default=0.0)
    production_date = models.DateTimeField(default=timezone.now)
    closed_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='open')
    variance = models.FloatField(default=0.0)
    wastes = models.FloatField(default=0.0)
    spills = models.FloatField(default=0.0)
    notes = models.TextField(blank=True, null=True)
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


class Formula(models.Model):
    finished_good = models.OneToOneField(
        Item,
        on_delete=models.CASCADE,
        related_name='formula',
        limit_choices_to={'item_type': 'finished_good'}
    )
    version = models.CharField(max_length=50, default='1.0')
    notes = models.TextField(blank=True, null=True)
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
    order_date = models.DateTimeField(auto_now_add=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.po_number


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='purchase_order_items', blank=True, null=True)
    # description field removed - not in database schema
    quantity_ordered = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    unit_price = models.FloatField(blank=True, null=True)
    # unit_cost removed - database only has unit_price, use unit_price instead
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['id']


class SalesOrder(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('received', 'Received'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    so_number = models.CharField(max_length=100, unique=True, db_index=True)
    customer_name = models.CharField(max_length=255)
    customer_id = models.CharField(max_length=100, blank=True, null=True)
    customer_reference_number = models.CharField(max_length=255, blank=True, null=True, help_text='Customer PO number or reference number')
    order_date = models.DateTimeField(auto_now_add=True)
    expected_ship_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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
    address = models.TextField(blank=True, null=True)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='pending')
    risk_profile = models.CharField(max_length=20, choices=RISK_PROFILE_CHOICES, default='2')
    risk_tier = models.CharField(max_length=20, choices=RISK_TIER_CHOICES, blank=True, null=True)
    on_time_performance = models.FloatField(default=100.0)
    quality_complaints = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    
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

