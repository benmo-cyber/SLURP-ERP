from rest_framework import serializers
from .models import (
    Item, Lot, ProductionBatch, ProductionBatchInput, ProductionBatchOutput, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, Vendor, VendorHistory, SupplierSurvey,
    SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification, Customer, CustomerPricing, VendorPricing, SalesOrderLot, Invoice, InvoiceItem,
    ShipToLocation, CustomerContact, SalesCall, CustomerForecast, LotDepletionLog, PurchaseOrderLog, ProductionLog,
    Shipment, ShipmentItem
)


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class LotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)
    received_date = serializers.DateTimeField(required=False, allow_null=True)
    quantity_remaining = serializers.SerializerMethodField()
    lot_number = serializers.CharField(required=False, read_only=True)
    
    class Meta:
        model = Lot
        fields = '__all__'
        extra_kwargs = {
            'quantity_remaining': {'required': False},
        }
    
    def get_quantity_remaining(self, obj):
        """Calculate quantity_remaining excluding sales allocations"""
        from django.db.models import Sum
        from .models import SalesOrderLot
        
        # Start with the lot's quantity_remaining
        remaining = obj.quantity_remaining
        
        # Subtract any allocations to sales orders
        try:
            allocated_to_sales = SalesOrderLot.objects.filter(
                lot=obj,
                sales_order_item__sales_order__status__in=[
                    'draft', 'allocated', 'issued', 'ready_for_shipment', 'shipped'
                ]
            ).aggregate(
                total=Sum('quantity_allocated')
            )['total'] or 0.0
            
            # Subtract allocated quantity from remaining
            remaining = max(0.0, remaining - allocated_to_sales)
        except Exception:
            # If SalesOrderLot table doesn't exist or there's an error, just return the original
            pass
        
        return remaining
    
    def create(self, validated_data):
        item_id = validated_data.pop('item_id')
        item = Item.objects.get(id=item_id)
        validated_data['item'] = item
        
        # Handle received_date - convert date string to datetime if needed
        received_date = validated_data.get('received_date')
        if received_date and isinstance(received_date, str):
            from django.utils.dateparse import parse_datetime, parse_date
            from django.utils import timezone
            # Try parsing as datetime first
            parsed = parse_datetime(received_date)
            if not parsed:
                # Try parsing as date and convert to datetime
                date_obj = parse_date(received_date)
                if date_obj:
                    parsed = timezone.make_aware(timezone.datetime.combine(date_obj, timezone.datetime.min.time()))
            if parsed:
                validated_data['received_date'] = parsed
            else:
                # If parsing fails, use current time
                validated_data['received_date'] = timezone.now()
        elif not received_date:
            # If no date provided, use current time
            from django.utils import timezone
            validated_data['received_date'] = timezone.now()
        
        # Set quantity_remaining based on status (remove from validated_data if present)
        validated_data.pop('quantity_remaining', None)  # Remove if present, we'll set it below
        status = validated_data.get('status', 'accepted')
        quantity = validated_data.get('quantity', 0)
        
        if status == 'accepted':
            validated_data['quantity_remaining'] = quantity
        elif status in ['rejected', 'on_hold']:
            validated_data['quantity_remaining'] = 0
            if status == 'on_hold':
                validated_data['on_hold'] = True
        else:
            # Default to quantity if status is not recognized
            validated_data['quantity_remaining'] = quantity
        
        # Generate lot number if not provided - but ONLY for non-raw materials
        # Raw materials should have their lot_number set to vendor_lot_number in the view
        if 'lot_number' not in validated_data or not validated_data.get('lot_number'):
            # Check if this is a raw material - if so, don't generate a lot number
            item_type = validated_data.get('item') and validated_data['item'].item_type
            if item_type != 'raw_material':
                from .views import generate_lot_number
                validated_data['lot_number'] = generate_lot_number()
        
        return super().create(validated_data)


class ProductionBatchInputSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = ProductionBatchInput
        fields = '__all__'


class ProductionBatchOutputSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = ProductionBatchOutput
        fields = '__all__'


class ProductionBatchSerializer(serializers.ModelSerializer):
    finished_good_item = ItemSerializer(read_only=True)
    finished_good_item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type__in=['finished_good', 'distributed_item', 'raw_material']),
        source='finished_good_item',
        write_only=True,
        required=False
    )
    inputs = ProductionBatchInputSerializer(many=True, read_only=True)
    outputs = ProductionBatchOutputSerializer(many=True, read_only=True)
    
    class Meta:
        model = ProductionBatch
        fields = '__all__'


class FormulaItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    
    class Meta:
        model = FormulaItem
        fields = '__all__'


class FormulaSerializer(serializers.ModelSerializer):
    finished_good = ItemSerializer(read_only=True)
    finished_good_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type='finished_good'),
        source='finished_good',
        write_only=True
    )
    ingredients = FormulaItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Formula
        fields = '__all__'


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    unit_cost = serializers.FloatField(source='unit_price', read_only=False, required=False, allow_null=True)
    
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'purchase_order', 'item', 'item_id', 'quantity_ordered', 'quantity_received', 
                  'unit_price', 'unit_cost', 'notes']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source='vendor_customer_name', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = '__all__'


class SalesOrderLotSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = SalesOrderLot
        fields = '__all__'


class SalesOrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    allocated_lots = SalesOrderLotSerializer(many=True, read_only=True)
    
    class Meta:
        model = SalesOrderItem
        fields = '__all__'


class ShipmentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentItem
        fields = '__all__'


class ShipmentSerializer(serializers.ModelSerializer):
    items = ShipmentItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Shipment
        fields = '__all__'


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, read_only=True)
    customer_detail = serializers.SerializerMethodField()
    shipments = ShipmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = SalesOrder
        fields = '__all__'
    
    def get_customer_detail(self, obj):
        if obj.customer:
            return CustomerSerializer(obj.customer).data
        return None


class CustomerSerializer(serializers.ModelSerializer):
    ship_to_locations_count = serializers.SerializerMethodField()
    contacts_count = serializers.SerializerMethodField()
    sales_calls_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = '__all__'
    
    def get_ship_to_locations_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_shiptolocation'")
                if cursor.fetchone() and hasattr(obj, 'ship_to_locations'):
                    return obj.ship_to_locations.filter(is_active=True).count()
        except Exception:
            pass
        return 0
    
    def get_contacts_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_customercontact'")
                if cursor.fetchone() and hasattr(obj, 'contacts'):
                    return obj.contacts.filter(is_active=True).count()
        except Exception:
            pass
        return 0
    
    def get_sales_calls_count(self, obj):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='erp_core_salescall'")
                if cursor.fetchone() and hasattr(obj, 'sales_calls'):
                    return obj.sales_calls.count()
        except Exception:
            pass
        return 0


class CustomerPricingSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.IntegerField(write_only=True, required=False)
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True, required=False)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = CustomerPricing
        fields = '__all__'
    
    def to_internal_value(self, data):
        # Make a mutable copy
        if hasattr(data, '_mutable'):
            data._mutable = True
        if not isinstance(data, dict):
            data = dict(data)
        else:
            data = data.copy()
        
        # Handle both 'customer' and 'customer_id' field names
        if 'customer' in data and 'customer_id' not in data:
            customer_val = data.get('customer')
            if customer_val is not None:
                data['customer_id'] = int(customer_val)
        
        # Handle both 'item' and 'item_id' field names  
        if 'item' in data and 'item_id' not in data:
            item_val = data.get('item')
            if item_val is not None:
                data['item_id'] = int(item_val)
        
        # Remove read_only fields before validation
        data.pop('customer', None)
        data.pop('item', None)
        
        return super().to_internal_value(data)
    
    def create(self, validated_data):
        import logging
        logger = logging.getLogger(__name__)
        
        # Get customer_id - check validated_data first, then initial_data
        customer_id = validated_data.pop('customer_id', None)
        if not customer_id and hasattr(self, 'initial_data'):
            customer_id = self.initial_data.get('customer') or self.initial_data.get('customer_id')
        
        if not customer_id:
            logger.error(f"Customer ID missing. validated_data keys: {validated_data.keys()}, initial_data: {getattr(self, 'initial_data', {})}")
            raise serializers.ValidationError({'customer': 'Customer is required'})
        
        try:
            validated_data['customer'] = Customer.objects.get(pk=int(customer_id))
        except (Customer.DoesNotExist, ValueError, TypeError) as e:
            logger.error(f"Customer lookup failed: {e}, customer_id: {customer_id}")
            raise serializers.ValidationError({'customer': f'Invalid customer ID: {customer_id}'})
        
        # Get item_id - check validated_data first, then initial_data
        item_id = validated_data.pop('item_id', None)
        if not item_id and hasattr(self, 'initial_data'):
            item_id = self.initial_data.get('item') or self.initial_data.get('item_id')
        
        if not item_id:
            logger.error(f"Item ID missing. validated_data keys: {validated_data.keys()}, initial_data: {getattr(self, 'initial_data', {})}")
            raise serializers.ValidationError({'item': 'Item is required'})
        
        try:
            validated_data['item'] = Item.objects.get(pk=int(item_id))
        except (Item.DoesNotExist, ValueError, TypeError) as e:
            logger.error(f"Item lookup failed: {e}, item_id: {item_id}")
            raise serializers.ValidationError({'item': f'Invalid item ID: {item_id}'})
        
        logger.info(f"Creating CustomerPricing with customer={validated_data.get('customer')}, item={validated_data.get('item')}, validated_data keys: {validated_data.keys()}")
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Extract and convert customer_id to customer ForeignKey
        customer_id = validated_data.pop('customer_id', None)
        if customer_id:
            try:
                validated_data['customer'] = Customer.objects.get(pk=int(customer_id))
            except (Customer.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError({'customer': f'Invalid customer ID: {customer_id}'})
        
        # Extract and convert item_id to item ForeignKey
        item_id = validated_data.pop('item_id', None)
        if item_id:
            try:
                validated_data['item'] = Item.objects.get(pk=int(item_id))
            except (Item.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError({'item': f'Invalid item ID: {item_id}'})
        
        return super().update(instance, validated_data)


class VendorPricingSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = VendorPricing
        fields = '__all__'
    
    def validate(self, data):
        # Handle both 'item' and 'item_id' field names
        item_id = data.pop('item_id', None) or self.initial_data.get('item')
        if item_id:
            try:
                data['item'] = Item.objects.get(pk=item_id)
            except Item.DoesNotExist:
                raise serializers.ValidationError({'item': 'Invalid item ID'})
        
        return data


class ShipToLocationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = ShipToLocation
        fields = '__all__'


class CustomerContactSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = CustomerContact
        fields = '__all__'


class SalesCallSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    contact_name = serializers.SerializerMethodField()
    
    class Meta:
        model = SalesCall
        fields = '__all__'
    
    def get_contact_name(self, obj):
        if obj.contact:
            return obj.contact.full_name
        return None


class CustomerForecastSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    item_sku = serializers.CharField(source='item.sku', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    
    class Meta:
        model = CustomerForecast
        fields = '__all__'


class InventoryTransactionSerializer(serializers.ModelSerializer):
    lot = LotSerializer(read_only=True)
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source='lot', write_only=True)
    
    class Meta:
        model = InventoryTransaction
        fields = '__all__'


class VendorHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorHistory
        fields = '__all__'


class SupplierSurveySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierSurvey
        fields = '__all__'


class SupplierDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierDocument
        fields = '__all__'


class TemporaryExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemporaryException
        fields = '__all__'


class VendorSerializer(serializers.ModelSerializer):
    history = VendorHistorySerializer(many=True, read_only=True)
    survey = SupplierSurveySerializer(read_only=True)
    documents = SupplierDocumentSerializer(many=True, read_only=True)
    exceptions = TemporaryExceptionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Vendor
        fields = '__all__'


class CostMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostMaster
        fields = '__all__'


class CostMasterHistorySerializer(serializers.ModelSerializer):
    cost_master_detail = CostMasterSerializer(source='cost_master', read_only=True)
    
    class Meta:
        model = CostMasterHistory
        fields = '__all__'


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'


class FinishedProductSpecificationSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type='finished_good'),
        source='item',
        write_only=True,
        required=False
    )
    fps_pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = FinishedProductSpecification
        fields = '__all__'
    
    def get_fps_pdf_url(self, obj):
        if obj.fps_pdf:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.fps_pdf.url)
            return obj.fps_pdf.url
        return None


class InvoiceItemSerializer(serializers.ModelSerializer):
    sales_order_item = SalesOrderItemSerializer(read_only=True)
    
    class Meta:
        model = InvoiceItem
        fields = '__all__'


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    sales_order = SalesOrderSerializer(read_only=True)
    days_aging = serializers.ReadOnlyField()
    
    class Meta:
        model = Invoice
        fields = '__all__'


class LotDepletionLogSerializer(serializers.ModelSerializer):
    lot_number_display = serializers.CharField(source='lot_number', read_only=True)
    item_sku_display = serializers.CharField(source='item_sku', read_only=True)
    item_name_display = serializers.CharField(source='item_name', read_only=True)
    depletion_method_display = serializers.CharField(source='get_depletion_method_display', read_only=True)
    
    class Meta:
        model = LotDepletionLog
        fields = '__all__'
        read_only_fields = ['depleted_at']


class PurchaseOrderLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    po_number_display = serializers.CharField(source='po_number', read_only=True)
    
    class Meta:
        model = PurchaseOrderLog
        fields = '__all__'
        read_only_fields = ['logged_at']


class ProductionLogSerializer(serializers.ModelSerializer):
    batch_number_display = serializers.CharField(source='batch_number', read_only=True)
    finished_good_sku_display = serializers.CharField(source='finished_good_sku', read_only=True)
    
    class Meta:
        model = ProductionLog
        fields = '__all__'
        read_only_fields = ['logged_at']

