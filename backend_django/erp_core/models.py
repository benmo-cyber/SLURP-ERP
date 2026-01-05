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
    
    sku = models.CharField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    item_type = models.CharField(max_length=50, choices=ITEM_TYPE_CHOICES)
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    approved_for_formulas = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sku']
    
    def __str__(self):
        return f"{self.sku} - {self.name}"


class LotNumberSequence(models.Model):
    date_prefix = models.CharField(max_length=6, unique=True)
    sequence_number = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date_prefix', '-sequence_number']


class Lot(models.Model):
    lot_number = models.CharField(max_length=20, unique=True, db_index=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='lots')
    quantity = models.FloatField()
    quantity_remaining = models.FloatField()
    received_date = models.DateTimeField()
    expiration_date = models.DateTimeField(blank=True, null=True)
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
    po_type = models.CharField(max_length=20, choices=PO_TYPE_CHOICES)
    vendor_customer_name = models.CharField(max_length=255)
    vendor_customer_id = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateTimeField(auto_now_add=True)
    expected_delivery_date = models.DateTimeField(blank=True, null=True)
    received_date = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.po_number


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='purchase_order_items')
    quantity_ordered = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    unit_price = models.FloatField(blank=True, null=True)
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

