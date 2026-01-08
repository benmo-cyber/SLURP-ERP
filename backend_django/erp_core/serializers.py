from rest_framework import serializers
from .models import (
    Item, Lot, ProductionBatch, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, Vendor, VendorHistory, SupplierSurvey,
    SupplierDocument, TemporaryException, CostMaster, CostMasterHistory, Account,
    FinishedProductSpecification
)


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class LotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)
    received_date = serializers.DateTimeField(required=False, allow_null=True)
    quantity_remaining = serializers.FloatField(required=False, allow_null=True)
    lot_number = serializers.CharField(required=False, read_only=True)
    
    class Meta:
        model = Lot
        fields = '__all__'
        extra_kwargs = {
            'quantity_remaining': {'required': False},
        }
    
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
        
        return super().create(validated_data)


class ProductionBatchSerializer(serializers.ModelSerializer):
    finished_good_item = ItemSerializer(read_only=True)
    finished_good_item_id = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.filter(item_type='finished_good'),
        source='finished_good_item',
        write_only=True
    )
    
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


class SalesOrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), source='item', write_only=True)
    
    class Meta:
        model = SalesOrderItem
        fields = '__all__'


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = SalesOrder
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

