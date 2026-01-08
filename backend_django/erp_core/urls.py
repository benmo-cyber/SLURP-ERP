from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet, LotViewSet, ProductionBatchViewSet,
    FormulaViewSet, PurchaseOrderViewSet, SalesOrderViewSet,
    InventoryTransactionViewSet, VendorViewSet,
    SupplierSurveyViewSet, SupplierDocumentViewSet, TemporaryExceptionViewSet,
    CostMasterViewSet, AccountViewSet, FinishedProductSpecificationViewSet
)

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'lots', LotViewSet)
router.register(r'production-batches', ProductionBatchViewSet)
router.register(r'formulas', FormulaViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'inventory-transactions', InventoryTransactionViewSet)
router.register(r'vendors', VendorViewSet)
router.register(r'supplier-surveys', SupplierSurveyViewSet)
router.register(r'supplier-documents', SupplierDocumentViewSet)
router.register(r'temporary-exceptions', TemporaryExceptionViewSet)
router.register(r'cost-master', CostMasterViewSet)
router.register(r'accounts', AccountViewSet)
router.register(r'finished-product-specifications', FinishedProductSpecificationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

