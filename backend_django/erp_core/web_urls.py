from django.urls import path

from erp_core.web_views.auth import HomeRedirectView, SlurpLoginView, SlurpLogoutView
from erp_core.web_views.examples import (
    ExampleBatchTicketView,
    ExampleDocumentsIndexView,
    ExampleInvoiceView,
    ExamplePackingListView,
)
from erp_core.web_views.finance import (
    AccountCreateView,
    AgingReportView,
    CostMasterCreateView,
    CustomerPricingCreateView,
    FinanceDashboardView,
    InvoiceDetailView,
    InvoiceStatusUpdateView,
    VendorPricingCreateView,
)
from erp_core.web_views.inventory import (
    CheckInView,
    InventoryDashboardView,
    ItemCreateView,
    ItemEditView,
    LotEditView,
    PurchaseOrderActionView,
    PurchaseOrderCreateView,
    PurchaseOrderDetailView,
    ReverseCheckInView,
)
from erp_core.web_views.production import (
    ProductionBatchCloseView,
    ProductionBatchCreateView,
    ProductionBatchDetailView,
    ProductionBatchReverseView,
    ProductionDashboardView,
)
from erp_core.web_views.quality import (
    FinishedGoodCreateView,
    LotTrackingView,
    QualityDashboardView,
    SupplierDocumentUploadView,
    TemporaryExceptionApproveView,
    TemporaryExceptionCreateView,
    VendorApproveView,
    VendorCreateView,
    VendorDetailView,
)
from erp_core.web_views.sales import (
    CalendarView,
    CustomerCreateView,
    CustomerDetailView,
    CustomerSubCreateView,
    SalesDashboardView,
    SalesOrderAllocateView,
    SalesOrderCheckoutView,
    SalesOrderCreateView,
    SalesOrderShipView,
)

urlpatterns = [
    path('', HomeRedirectView.as_view(), name='home'),
    path('login/', SlurpLoginView.as_view(), name='login'),
    path('logout/', SlurpLogoutView.as_view(), name='logout'),

    # Inventory
    path('inventory/', InventoryDashboardView.as_view(), name='inventory_dashboard'),
    path('inventory/items/new/', ItemCreateView.as_view(), name='item_create'),
    path('inventory/items/<int:pk>/edit/', ItemEditView.as_view(), name='item_edit'),
    path('inventory/check-in/', CheckInView.as_view(), name='check_in'),
    path('inventory/reverse-check-in/', ReverseCheckInView.as_view(), name='reverse_check_in'),
    path('inventory/lots/<int:pk>/edit/', LotEditView.as_view(), name='lot_edit'),
    path('inventory/purchase-orders/new/', PurchaseOrderCreateView.as_view(), name='po_create'),
    path('inventory/purchase-orders/<int:pk>/', PurchaseOrderDetailView.as_view(), name='po_detail'),
    path('inventory/purchase-orders/<int:pk>/<str:action>/', PurchaseOrderActionView.as_view(), name='po_action'),

    # Production
    path('production/', ProductionDashboardView.as_view(), name='production_dashboard'),
    path('production/batches/new/', ProductionBatchCreateView.as_view(), name='production_batch_create'),
    path('production/batches/<int:pk>/', ProductionBatchDetailView.as_view(), name='production_batch_detail'),
    path('production/batches/<int:pk>/close/', ProductionBatchCloseView.as_view(), name='production_batch_close'),
    path('production/batches/<int:pk>/reverse/', ProductionBatchReverseView.as_view(), name='production_batch_reverse'),

    # Quality
    path('quality/', QualityDashboardView.as_view(), name='quality_dashboard'),
    path('quality/vendors/new/', VendorCreateView.as_view(), name='vendor_create'),
    path('quality/vendors/<int:pk>/', VendorDetailView.as_view(), name='vendor_detail'),
    path('quality/vendors/<int:pk>/approve/', VendorApproveView.as_view(), name='vendor_approve'),
    path('quality/vendors/<int:vendor_pk>/exceptions/', TemporaryExceptionCreateView.as_view(), name='exception_create'),
    path('quality/exceptions/<int:pk>/approve/', TemporaryExceptionApproveView.as_view(), name='exception_approve'),
    path('quality/vendors/<int:vendor_pk>/documents/', SupplierDocumentUploadView.as_view(), name='document_upload'),
    path('quality/finished-goods/new/', FinishedGoodCreateView.as_view(), name='finished_good_create'),
    path('quality/lot-tracking/', LotTrackingView.as_view(), name='lot_tracking'),

    # Sales
    path('sales/', SalesDashboardView.as_view(), name='sales_dashboard'),
    path('sales/customers/new/', CustomerCreateView.as_view(), name='customer_create'),
    path('sales/customers/<int:pk>/', CustomerDetailView.as_view(), name='customer_detail'),
    path('sales/customers/<int:customer_pk>/<str:sub_type>/', CustomerSubCreateView.as_view(), name='customer_sub_create'),
    path('sales/orders/new/', SalesOrderCreateView.as_view(), name='sales_order_create'),
    path('sales/orders/<int:pk>/checkout/', SalesOrderCheckoutView.as_view(), name='sales_order_checkout'),
    path('sales/orders/<int:pk>/allocate/', SalesOrderAllocateView.as_view(), name='sales_order_allocate'),
    path('sales/orders/<int:pk>/ship/', SalesOrderShipView.as_view(), name='sales_order_ship'),
    path('sales/calendar/', CalendarView.as_view(), name='calendar'),

    # Finance
    path('finance/', FinanceDashboardView.as_view(), name='finance_dashboard'),
    path('finance/accounts/new/', AccountCreateView.as_view(), name='account_create'),
    path('finance/invoices/<int:pk>/', InvoiceDetailView.as_view(), name='invoice_detail'),
    path('finance/invoices/<int:pk>/status/', InvoiceStatusUpdateView.as_view(), name='invoice_status'),
    path('finance/cost-master/new/', CostMasterCreateView.as_view(), name='cost_master_create'),
    path('finance/vendor-pricing/new/', VendorPricingCreateView.as_view(), name='vendor_pricing_create'),
    path('finance/customer-pricing/new/', CustomerPricingCreateView.as_view(), name='customer_pricing_create'),
    path('finance/aging/', AgingReportView.as_view(), name='aging_report'),

    # Example printable documents
    path('examples/', ExampleDocumentsIndexView.as_view(), name='example_documents'),
    path('examples/batch-ticket/', ExampleBatchTicketView.as_view(), name='example_batch_ticket'),
    path('examples/packing-list/', ExamplePackingListView.as_view(), name='example_packing_list'),
    path('examples/invoice/', ExampleInvoiceView.as_view(), name='example_invoice'),
]
