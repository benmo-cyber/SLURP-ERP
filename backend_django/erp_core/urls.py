from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet, ItemPackSizeViewSet, LotViewSet, ProductionBatchViewSet,
    FormulaViewSet, PurchaseOrderViewSet, SalesOrderViewSet,
    InventoryTransactionViewSet, VendorViewSet,
    SupplierSurveyViewSet, SupplierDocumentViewSet, TemporaryExceptionViewSet,
    CostMasterViewSet, AccountViewSet, FinishedProductSpecificationViewSet,
    InvoiceViewSet, CalendarEventsViewSet, CustomerViewSet, CustomerPricingViewSet, VendorPricingViewSet,
    ShipToLocationViewSet, CustomerContactViewSet, SalesCallViewSet,
    CustomerForecastViewSet, CustomerUsageViewSet, LotDepletionLogViewSet, LotTransactionLogViewSet,
    PurchaseOrderLogViewSet, ProductionLogViewSet, CheckInLogViewSet, FiscalPeriodViewSet, JournalEntryViewSet,
    GeneralLedgerViewSet, AccountBalanceViewSet, FinancialReportsViewSet,
    AccountsPayableViewSet, AccountsReceivableViewSet, PaymentViewSet
)

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'item-pack-sizes', ItemPackSizeViewSet, basename='item-pack-sizes')
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
router.register(r'lot-depletion-logs', LotDepletionLogViewSet, basename='lot-depletion-logs')
router.register(r'lot-transaction-logs', LotTransactionLogViewSet, basename='lot-transaction-logs')
router.register(r'purchase-order-logs', PurchaseOrderLogViewSet, basename='purchase-order-logs')
router.register(r'production-logs', ProductionLogViewSet, basename='production-logs')
router.register(r'check-in-logs', CheckInLogViewSet, basename='check-in-logs')
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-periods')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entries')
router.register(r'general-ledger', GeneralLedgerViewSet, basename='general-ledger')
router.register(r'account-balances', AccountBalanceViewSet, basename='account-balances')
router.register(r'financial-reports', FinancialReportsViewSet, basename='financial-reports')
router.register(r'accounts-payable', AccountsPayableViewSet, basename='accounts-payable')
router.register(r'accounts-receivable', AccountsReceivableViewSet, basename='accounts-receivable')
router.register(r'payments', PaymentViewSet, basename='payments')

urlpatterns = [
    path('', include(router.urls)),
]

