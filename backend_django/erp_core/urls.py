from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import auth_views
from .address_suggest import address_suggest
from .sample_xml_import import import_private_sample_xml_api
from .views import (
    ItemViewSet, ItemPackSizeViewSet, LotViewSet, CampaignLotViewSet, ProductionBatchViewSet,
    ItemCoaTestLineViewSet, LotCoaCertificateViewSet, LotCoaCustomerCopyViewSet,
    CriticalControlPointViewSet, FormulaViewSet, RDFormulaViewSet, PurchaseOrderViewSet, PurchaseOrderItemViewSet, SalesOrderViewSet,
    ShipmentViewSet,
    InventoryTransactionViewSet, VendorViewSet, VendorContactViewSet,
    SupplierSurveyViewSet, SupplierDocumentViewSet, TemporaryExceptionViewSet,
    CostMasterViewSet, AccountViewSet, FinishedProductSpecificationViewSet,
    InvoiceViewSet, CalendarEventsViewSet, CustomerViewSet, CustomerPricingViewSet, VendorPricingViewSet,
    ShipToLocationViewSet, CustomerContactViewSet, SalesCallViewSet,
    CustomerForecastViewSet, CustomerUsageViewSet, LotDepletionLogViewSet, LotTransactionLogViewSet,
    PurchaseOrderLogViewSet, ProductionLogViewSet, CheckInLogViewSet, LotAttributeChangeLogViewSet, FiscalPeriodViewSet, JournalEntryViewSet,
    GeneralLedgerViewSet, AccountBalanceViewSet, FinancialReportsViewSet,
    AccountsPayableViewSet, AccountsReceivableViewSet, PaymentViewSet, BankReconciliationViewSet
)

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'item-pack-sizes', ItemPackSizeViewSet, basename='item-pack-sizes')
router.register(r'item-coa-test-lines', ItemCoaTestLineViewSet, basename='item-coa-test-lines')
router.register(r'lot-coa-certificates', LotCoaCertificateViewSet, basename='lot-coa-certificates')
router.register(r'lot-coa-customer-copies', LotCoaCustomerCopyViewSet, basename='lot-coa-customer-copies')
router.register(r'lots', LotViewSet)
router.register(r'campaign-lots', CampaignLotViewSet, basename='campaign-lots')
router.register(r'production-batches', ProductionBatchViewSet)
router.register(r'critical-control-points', CriticalControlPointViewSet)
router.register(r'formulas', FormulaViewSet)
router.register(r'rd-formulas', RDFormulaViewSet, basename='rd-formulas')
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'purchase-order-items', PurchaseOrderItemViewSet, basename='purchase-order-items')
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'shipments', ShipmentViewSet, basename='shipments')
router.register(r'inventory-transactions', InventoryTransactionViewSet)
router.register(r'vendors', VendorViewSet)
router.register(r'vendor-contacts', VendorContactViewSet, basename='vendor-contacts')
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
router.register(r'lot-attribute-change-logs', LotAttributeChangeLogViewSet, basename='lot-attribute-change-logs')
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-periods')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entries')
router.register(r'general-ledger', GeneralLedgerViewSet, basename='general-ledger')
router.register(r'account-balances', AccountBalanceViewSet, basename='account-balances')
router.register(r'financial-reports', FinancialReportsViewSet, basename='financial-reports')
router.register(r'accounts-payable', AccountsPayableViewSet, basename='accounts-payable')
router.register(r'accounts-receivable', AccountsReceivableViewSet, basename='accounts-receivable')
router.register(r'payments', PaymentViewSet, basename='payments')
router.register(r'bank-reconciliations', BankReconciliationViewSet, basename='bank-reconciliations')

urlpatterns = [
    path('address-suggest/', address_suggest, name='address-suggest'),
    path('import-private-sample-xml/', import_private_sample_xml_api, name='import-private-sample-xml'),
    path('', include(router.urls)),
    path('auth/csrf/', auth_views.csrf_token),
    path('auth/login/', auth_views.login_view),
    path('auth/logout/', auth_views.logout_view),
    path('auth/me/', auth_views.me),
    path('auth/password-reset/', auth_views.password_reset_request),
    path('auth/password-reset-confirm/<str:uidb64>/<str:token>/', auth_views.password_reset_confirm_api),
]

