from rest_framework import serializers
from .models import (
    Item, ItemPackSize, Lot, ProductionBatch, ProductionBatchInput, ProductionBatchOutput, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, Vendor, VendorHistory, SupplierSurvey,
    SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification, Customer, CustomerPricing, VendorPricing, SalesOrderLot, Invoice, InvoiceItem,
    ShipToLocation, CustomerContact, SalesCall, CustomerForecast, LotDepletionLog, LotTransactionLog, PurchaseOrderLog, ProductionLog, CheckInLog,
    Shipment, ShipmentItem, AccountsPayable, AccountsReceivable, Payment, FiscalPeriod, JournalEntry, JournalEntryLine, GeneralLedgerEntry, AccountBalance
)


class ItemPackSizeSerializer(serializers.ModelSerializer):
    pack_size_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ItemPackSize
        fields = '__all__'
    
    def get_pack_size_display(self, obj):
        """Return formatted pack size string"""
        return f"{obj.pack_size} {obj.pack_size_unit}"


class ItemSerializer(serializers.ModelSerializer):
    display_name_for_vendor = serializers.SerializerMethodField()
    
    def get_display_name_for_vendor(self, obj):
        """Returns vendor_item_name if available and item has a vendor, otherwise returns name"""
        if obj.vendor_item_name and obj.vendor:
            return obj.vendor_item_name
        return obj.name
    pack_sizes = serializers.SerializerMethodField()
    default_pack_size = serializers.SerializerMethodField()
    
    class Meta:
        model = Item
        fields = '__all__'
    
    def get_pack_sizes(self, obj):
        """Return all active pack sizes for this item"""
        active_pack_sizes = obj.pack_sizes.filter(is_active=True)
        return ItemPackSizeSerializer(active_pack_sizes, many=True).data
    
    def get_default_pack_size(self, obj):
        """Return the default pack size for this item"""
        default = obj.pack_sizes.filter(is_default=True, is_active=True).first()
        if default:
            return ItemPackSizeSerializer(default).data
        return None


class LotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)
    pack_size_obj = ItemPackSizeSerializer(read_only=True, source='pack_size')
    pack_size_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    received_date = serializers.DateTimeField(required=False, allow_null=True)
    quantity_remaining = serializers.SerializerMethodField()
    lot_number = serializers.CharField(required=False, allow_blank=False)
    
    class Meta:
        model = Lot
        fields = '__all__'
        extra_kwargs = {
            'quantity_remaining': {'required': False},
        }
    
    def get_quantity_remaining(self, obj):
        """Calculate quantity_remaining excluding sales allocations
        
        Note: The lot's quantity_remaining in the database already reflects shipped quantities.
        We only need to subtract allocations for orders that haven't been shipped yet.
        """
        from django.db.models import Sum
        from .models import SalesOrderLot
        
        # Start with the lot's quantity_remaining (already accounts for shipped material)
        remaining = obj.quantity_remaining
        
        # Only subtract allocations for orders that haven't been shipped yet
        # (shipped orders already reduced the lot's quantity_remaining)
        try:
            allocated_to_sales = SalesOrderLot.objects.filter(
                lot=obj,
                sales_order_item__sales_order__status__in=[
                    'draft', 'allocated', 'issued', 'ready_for_shipment'
                    # Note: 'shipped' orders already reduced quantity_remaining, so don't subtract again
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
        
        # Ensure lot_number is set - database requires NOT NULL
        # If not provided, it should have been set in the view's create method
        # But as a safety fallback, generate one if still missing
        if not validated_data.get('lot_number'):
            # Import here to avoid circular import
            from django.db import transaction
            from django.utils import timezone
            from .models import LotNumberSequence, Lot
            
            today = timezone.now()
            year_prefix = today.strftime('%y')
            
            with transaction.atomic():
                sequence, created = LotNumberSequence.objects.select_for_update().get_or_create(
                    year_prefix=year_prefix,
                    defaults={'sequence_number': 0}
                )
                sequence.sequence_number += 1
                sequence.save()
                lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
                
                # Ensure uniqueness
                max_retries = 10
                retry_count = 0
                while Lot.objects.filter(lot_number=lot_number).exists() and retry_count < max_retries:
                    sequence.sequence_number += 1
                    sequence.save()
                    lot_number = f"1{year_prefix}{sequence.sequence_number:05d}"
                    retry_count += 1
            
            validated_data['lot_number'] = lot_number
        
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
    customer = serializers.SerializerMethodField()  # Add customer field for frontend compatibility
    shipments = ShipmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = SalesOrder
        fields = '__all__'
    
    def get_customer_detail(self, obj):
        if obj.customer:
            return CustomerSerializer(obj.customer).data
        return None
    
    def get_customer(self, obj):
        """Get customer data including payment_terms"""
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
    sales_order = serializers.SerializerMethodField()
    days_aging = serializers.SerializerMethodField()  # Changed to SerializerMethodField to handle manually created objects
    # Map database field names to expected frontend field names
    tax = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()
    freight = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    # Add customer_name and payment_terms from invoice or sales order
    customer_name = serializers.SerializerMethodField()
    payment_terms = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = '__all__'
    
    def get_days_aging(self, obj):
        """Calculate days aging - handle manually created invoice objects"""
        try:
            # Try to use the property if it exists
            if hasattr(obj, 'days_aging'):
                return obj.days_aging
            # Otherwise calculate manually
            from django.utils import timezone
            if obj.status == 'paid':
                return 0
            if not hasattr(obj, 'due_date') or not obj.due_date:
                return 0
            today = timezone.now().date()
            return (today - obj.due_date).days
        except Exception:
            return 0
    
    def get_customer_name(self, obj):
        """Get customer name from invoice or sales order"""
        # First try to get from invoice's customer_vendor_name field
        if hasattr(obj, 'customer_vendor_name') and obj.customer_vendor_name:
            return obj.customer_vendor_name
        # Fall back to sales order
        if hasattr(obj, 'sales_order') and obj.sales_order:
            if hasattr(obj.sales_order, 'customer_name') and obj.sales_order.customer_name:
                return obj.sales_order.customer_name
            if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer:
                return obj.sales_order.customer.name
        return None
    
    def get_payment_terms(self, obj):
        """Get payment terms from sales order customer"""
        if hasattr(obj, 'sales_order') and obj.sales_order:
            if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer:
                return getattr(obj.sales_order.customer, 'payment_terms', None)
        return None
    
    def get_tax(self, obj):
        """Map tax_amount to tax for frontend compatibility"""
        return getattr(obj, 'tax_amount', getattr(obj, 'tax', 0.0))
    
    def get_grand_total(self, obj):
        """Map total_amount to grand_total for frontend compatibility"""
        return getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0.0))
    
    def get_freight(self, obj):
        """Get freight - may not exist in database"""
        return getattr(obj, 'freight', 0.0)
    
    def get_discount(self, obj):
        """Get discount - may not exist in database"""
        return getattr(obj, 'discount', 0.0)
    
    def get_sales_order(self, obj):
        """Get sales order - handle case where sales_order_id column doesn't exist"""
        from .models import SalesOrder
        try:
            # Strategy 1: If sales_order is already attached to the object, use it (but ensure customer is loaded)
            if hasattr(obj, 'sales_order') and obj.sales_order is not None:
                # Check if customer is loaded
                if hasattr(obj.sales_order, 'customer') and obj.sales_order.customer is not None:
                    # Customer is loaded, serialize it
                    return SalesOrderSerializer(obj.sales_order).data
                else:
                    # Customer not loaded, reload with customer
                    try:
                        so = SalesOrder.objects.select_related('customer').get(id=obj.sales_order.id)
                        return SalesOrderSerializer(so).data
                    except SalesOrder.DoesNotExist:
                        # Sales order was deleted, return None
                        return None
            
            # Strategy 2: Get sales_order_id from any source and load it
            sales_order_id = None
            if hasattr(obj, 'sales_order_id') and obj.sales_order_id:
                sales_order_id = obj.sales_order_id
            elif hasattr(obj, '_sales_order_id') and obj._sales_order_id:
                sales_order_id = obj._sales_order_id
            
            if sales_order_id:
                try:
                    so = SalesOrder.objects.select_related('customer').get(id=sales_order_id)
                    return SalesOrderSerializer(so).data
                except SalesOrder.DoesNotExist:
                    # Sales order doesn't exist
                    return None
            
            # Strategy 3: Try to find from notes (fallback for old invoices)
            if hasattr(obj, 'notes') and obj.notes:
                import re
                # Look for "sales order {so_number}" or "from sales order {id}"
                match = re.search(r'sales order[:\s]+([A-Z0-9-]+)', obj.notes, re.IGNORECASE)
                if match:
                    so_identifier = match.group(1)
                    try:
                        # Try as SO number first
                        so = SalesOrder.objects.select_related('customer').get(so_number=so_identifier)
                        return SalesOrderSerializer(so).data
                    except SalesOrder.DoesNotExist:
                        try:
                            # Try as ID
                            so = SalesOrder.objects.select_related('customer').get(id=int(so_identifier))
                            return SalesOrderSerializer(so).data
                        except (ValueError, SalesOrder.DoesNotExist):
                            pass
            
            return None
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting sales order for invoice {getattr(obj, 'invoice_number', 'unknown')}: {e}")
            logger.error(traceback.format_exc())
            return None


class LotTransactionLogSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    
    class Meta:
        model = LotTransactionLog
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


class FiscalPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalPeriod
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class JournalEntryLineSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    
    class Meta:
        model = JournalEntryLine
        fields = '__all__'


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalEntryLineSerializer(many=True, read_only=True)
    total_debits = serializers.SerializerMethodField()
    total_credits = serializers.SerializerMethodField()
    is_balanced = serializers.SerializerMethodField()
    
    class Meta:
        model = JournalEntry
        fields = '__all__'
        read_only_fields = ['entry_number', 'created_at', 'updated_at', 'posted_at']
    
    def get_total_debits(self, obj):
        return sum(line.amount for line in obj.lines.filter(debit_credit='debit'))
    
    def get_total_credits(self, obj):
        return sum(line.amount for line in obj.lines.filter(debit_credit='credit'))
    
    def get_is_balanced(self, obj):
        return abs(self.get_total_debits(obj) - self.get_total_credits(obj)) < 0.01


class GeneralLedgerEntrySerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    journal_entry_number = serializers.CharField(source='journal_entry.entry_number', read_only=True)
    
    class Meta:
        model = GeneralLedgerEntry
        fields = '__all__'
        read_only_fields = ['created_at']


class AccountBalanceSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source='account.account_number', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    period_name = serializers.CharField(source='fiscal_period.period_name', read_only=True)
    
    class Meta:
        model = AccountBalance
        fields = '__all__'
        read_only_fields = ['last_updated']


class AccountsPayableSerializer(serializers.ModelSerializer):
    days_aging = serializers.ReadOnlyField()
    aging_bucket = serializers.ReadOnlyField()
    vendor_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AccountsPayable
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'balance', 'status', 'days_aging', 'aging_bucket']
    
    def get_vendor_display(self, obj):
        return obj.vendor_name


class AccountsReceivableSerializer(serializers.ModelSerializer):
    days_aging = serializers.ReadOnlyField()
    aging_bucket = serializers.ReadOnlyField()
    customer_display = serializers.SerializerMethodField()
    invoice_number_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AccountsReceivable
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'balance', 'status', 'days_aging', 'aging_bucket']
    
    def get_customer_display(self, obj):
        return obj.customer_name
    
    def get_invoice_number_display(self, obj):
        try:
            return obj.invoice.invoice_number if obj.invoice else None
        except Exception:
            # If invoice is not loaded, try to get it from the invoice_id
            if hasattr(obj, 'invoice_id') and obj.invoice_id:
                from .models import Invoice
                try:
                    invoice = Invoice.objects.get(id=obj.invoice_id)
                    return invoice.invoice_number
                except Invoice.DoesNotExist:
                    return None
            return None


class PaymentSerializer(serializers.ModelSerializer):
    ap_entry_display = serializers.SerializerMethodField()
    ar_entry_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_ap_entry_display(self, obj):
        if obj.ap_entry:
            return f"{obj.ap_entry.vendor_name} - ${obj.ap_entry.balance}"
        return None
    
    def get_ar_entry_display(self, obj):
        if obj.ar_entry:
            return f"{obj.ar_entry.customer_name} - ${obj.ar_entry.balance}"
        return None


class ProductionLogSerializer(serializers.ModelSerializer):
    batch_number_display = serializers.CharField(source='batch_number', read_only=True)
    finished_good_sku_display = serializers.CharField(source='finished_good_sku', read_only=True)
    
    class Meta:
        model = ProductionLog
        fields = '__all__'
        read_only_fields = ['logged_at']


class CheckInLogSerializer(serializers.ModelSerializer):
    item_display = serializers.SerializerMethodField()
    lot_number_display = serializers.CharField(source='lot_number', read_only=True)
    
    class Meta:
        model = CheckInLog
        fields = '__all__'
        read_only_fields = ['checked_in_at']
    
    def get_item_display(self, obj):
        return f"{obj.item_sku} - {obj.item_name}"

