from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet, LotViewSet, ProductionBatchViewSet,
    FormulaViewSet, PurchaseOrderViewSet, SalesOrderViewSet,
    InventoryTransactionViewSet, VendorViewSet,
    SupplierSurveyViewSet, SupplierDocumentViewSet, TemporaryExceptionViewSet,
    CostMasterViewSet, AccountViewSet, FinishedProductSpecificationViewSet,
    InvoiceViewSet, CalendarEventsViewSet, CustomerViewSet, CustomerPricingViewSet, VendorPricingViewSet,
    ShipToLocationViewSet, CustomerContactViewSet, SalesCallViewSet,
    CustomerForecastViewSet, CustomerUsageViewSet
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
router.register(r'invoices', InvoiceViewSet)
router.register(r'calendar', CalendarEventsViewSet, basename='calendar')
router.register(r'customers', CustomerViewSet)
router.register(r'customer-pricing', CustomerPricingViewSet)
router.register(r'vendor-pricing', VendorPricingViewSet)
router.register(r'ship-to-locations', ShipToLocationViewSet)
router.register(r'customer-contacts', CustomerContactViewSet)
router.register(r'sales-calls', SalesCallViewSet)
router.register(r'customer-forecasts', CustomerForecastViewSet)
router.register(r'customer-usage', CustomerUsageViewSet, basename='customer-usage')

urlpatterns = [
    path('', include(router.urls)),
]

