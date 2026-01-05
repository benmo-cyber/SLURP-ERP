from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet, LotViewSet, ProductionBatchViewSet,
    FormulaViewSet, PurchaseOrderViewSet, SalesOrderViewSet,
    InventoryTransactionViewSet
)

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'lots', LotViewSet)
router.register(r'production-batches', ProductionBatchViewSet)
router.register(r'formulas', FormulaViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'inventory-transactions', InventoryTransactionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

