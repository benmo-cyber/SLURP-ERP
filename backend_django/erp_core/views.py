from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime
from .models import (
    Item, Lot, ProductionBatch, Formula, FormulaItem,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem,
    InventoryTransaction, LotNumberSequence
)
from .serializers import (
    ItemSerializer, LotSerializer, ProductionBatchSerializer,
    FormulaSerializer, FormulaItemSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    SalesOrderSerializer, SalesOrderItemSerializer,
    InventoryTransactionSerializer
)


def generate_lot_number():
    """Generate a unique lot number in format YYMMDD######"""
    today = timezone.now()
    date_prefix = today.strftime('%y%m%d')
    
    # Get or create sequence for today
    sequence, created = LotNumberSequence.objects.get_or_create(
        date_prefix=date_prefix,
        defaults={'sequence_number': 0}
    )
    
    # Increment sequence
    sequence.sequence_number += 1
    sequence.save()
    
    # Format: YYMMDD + 6-digit sequence
    lot_number = f"{date_prefix}{sequence.sequence_number:06d}"
    return lot_number


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer


class LotViewSet(viewsets.ModelViewSet):
    queryset = Lot.objects.select_related('item').all()
    serializer_class = LotSerializer
    
    def create(self, request, *args, **kwargs):
        # Generate lot number automatically
        lot_number = generate_lot_number()
        
        # Create the lot
        serializer = self.get_serializer(data={
            **request.data,
            'lot_number': lot_number,
        })
        serializer.is_valid(raise_exception=True)
        lot = serializer.save()
        
        # Create inventory transaction for receipt
        InventoryTransaction.objects.create(
            transaction_type='receipt',
            lot=lot,
            quantity=lot.quantity,
        )
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ProductionBatchViewSet(viewsets.ModelViewSet):
    queryset = ProductionBatch.objects.select_related('finished_good_item').all()
    serializer_class = ProductionBatchSerializer


class FormulaViewSet(viewsets.ModelViewSet):
    queryset = Formula.objects.select_related('finished_good').prefetch_related('ingredients__item').all()
    serializer_class = FormulaSerializer


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.prefetch_related('items__item').all()
    serializer_class = PurchaseOrderSerializer


class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.prefetch_related('items__item').all()
    serializer_class = SalesOrderSerializer


class InventoryTransactionViewSet(viewsets.ModelViewSet):
    queryset = InventoryTransaction.objects.select_related('lot__item').all()
    serializer_class = InventoryTransactionSerializer

