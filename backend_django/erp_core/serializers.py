from rest_framework import serializers
from .models import (
    Item, Lot, ProductionBatch, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction
)


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class LotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Lot
        fields = '__all__'
    
    def create(self, validated_data):
        item_id = validated_data.pop('item_id')
        item = Item.objects.get(id=item_id)
        validated_data['item'] = item
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
    
    class Meta:
        model = PurchaseOrderItem
        fields = '__all__'


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    
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

