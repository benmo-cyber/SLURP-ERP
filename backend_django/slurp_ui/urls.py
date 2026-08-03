from django.urls import path

from . import views

app_name = "slurp_ui"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path(
        "reset-password/<uidb64>/<token>/",
        views.reset_password,
        name="reset_password",
    ),
    path("god-mode/", views.toggle_god_mode, name="toggle_god_mode"),
    path("import-sample-xml/", views.import_sample_xml, name="import_sample_xml"),
    # Inventory
    path("", views.inventory_table, name="home"),
    path("inventory/", views.inventory_table, name="inventory"),
    path("inventory/items/", views.inventory_items, name="inventory_items"),
    path(
        "inventory/purchase-orders/",
        views.inventory_purchase_orders,
        name="inventory_purchase_orders",
    ),
    path(
        "inventory/purchase-orders/<int:pk>/pdf/",
        views.inventory_po_pdf,
        name="inventory_po_pdf",
    ),
    path(
        "inventory/purchase-orders/<int:pk>/cancel/",
        views.inventory_cancel_po,
        name="inventory_cancel_po",
    ),
    path(
        "inventory/purchase-orders/<int:pk>/revise/",
        views.inventory_revise_po,
        name="inventory_revise_po",
    ),
    path(
        "inventory/purchase-orders/<int:pk>/issue/",
        views.inventory_issue_po,
        name="inventory_issue_po",
    ),
    path("inventory/logs/", views.inventory_logs, name="inventory_logs"),
    path("inventory/check-in/", views.inventory_check_in, name="inventory_check_in"),
    path(
        "inventory/create-item/",
        views.inventory_create_item,
        name="inventory_create_item",
    ),
    path(
        "inventory/items/<int:pk>/edit/",
        views.inventory_edit_item,
        name="inventory_edit_item",
    ),
    path("inventory/create-po/", views.inventory_create_po, name="inventory_create_po"),
    path(
        "inventory/indirect-checkout/",
        views.inventory_indirect_checkout,
        name="inventory_indirect_checkout",
    ),
    path(
        "inventory/reverse-check-in/",
        views.inventory_reverse_check_in,
        name="inventory_reverse_check_in",
    ),
    path(
        "inventory/lots/<int:pk>/hold/",
        views.inventory_lot_hold,
        name="inventory_lot_hold",
    ),
    path(
        "inventory/lots/<int:pk>/release/",
        views.inventory_lot_release,
        name="inventory_lot_release",
    ),
    path(
        "inventory/lots/<int:pk>/reconcile/",
        views.inventory_lot_reconcile,
        name="inventory_lot_reconcile",
    ),
    # Sales
    path("sales/", views.sales_crm, name="sales"),
    path("sales/orders/", views.sales_orders, name="sales_orders"),
    path("sales/calendar/", views.sales_calendar, name="sales_calendar"),
    path("sales/customers/", views.sales_customers, name="sales_customers"),
    path(
        "sales/customers/<int:pk>/",
        views.sales_customer_profile,
        name="sales_customer_profile",
    ),
    path(
        "sales/customers/<int:customer_pk>/ship-to/new/",
        views.sales_customer_ship_to,
        name="sales_customer_ship_to_new",
    ),
    path(
        "sales/customers/<int:customer_pk>/ship-to/<int:pk>/edit/",
        views.sales_customer_ship_to,
        name="sales_customer_ship_to_edit",
    ),
    path(
        "sales/customers/<int:customer_pk>/contacts/new/",
        views.sales_customer_contact,
        name="sales_customer_contact_new",
    ),
    path(
        "sales/customers/<int:customer_pk>/contacts/<int:pk>/edit/",
        views.sales_customer_contact,
        name="sales_customer_contact_edit",
    ),
    path(
        "sales/customers/<int:customer_pk>/sales-calls/new/",
        views.sales_customer_call,
        name="sales_customer_call_new",
    ),
    path(
        "sales/customers/<int:customer_pk>/sales-calls/<int:pk>/edit/",
        views.sales_customer_call,
        name="sales_customer_call_edit",
    ),
    path(
        "sales/customers/<int:customer_pk>/forecasts/new/",
        views.sales_customer_forecast,
        name="sales_customer_forecast_new",
    ),
    path(
        "sales/customers/<int:customer_pk>/forecasts/<int:pk>/edit/",
        views.sales_customer_forecast,
        name="sales_customer_forecast_edit",
    ),
    path(
        "sales/customers/<int:customer_pk>/pricing/new/",
        views.sales_customer_pricing,
        name="sales_customer_pricing_new",
    ),
    path(
        "sales/customers/<int:customer_pk>/pricing/<int:pk>/edit/",
        views.sales_customer_pricing,
        name="sales_customer_pricing_edit",
    ),
    path("sales/checkout/", views.sales_checkout, name="sales_checkout"),
    path(
        "sales/combined-checkout/",
        views.sales_combined_checkout,
        name="sales_combined_checkout",
    ),
    path(
        "sales/combined-packing-list/",
        views.sales_combined_packing_list_pdf,
        name="sales_combined_packing_list_pdf",
    ),
    path("sales/create-order/", views.sales_create_order, name="sales_create_order"),
    path(
        "sales/orders/<int:pk>/issue/",
        views.sales_issue_order,
        name="sales_issue_order",
    ),
    path(
        "sales/orders/<int:pk>/allocate/",
        views.sales_allocate_order,
        name="sales_allocate_order",
    ),
    path(
        "sales/orders/<int:pk>/pick-list/",
        views.sales_pick_list_pdf,
        name="sales_pick_list_pdf",
    ),
    path(
        "sales/orders/<int:pk>/packing-list/",
        views.sales_packing_list_pdf,
        name="sales_packing_list_pdf",
    ),
    path(
        "sales/orders/<int:pk>/",
        views.sales_order_detail,
        name="sales_order_detail",
    ),
    path(
        "sales/orders/<int:pk>/revert/",
        views.sales_revert_order,
        name="sales_revert_order",
    ),
    path(
        "sales/shipments/<int:pk>/reverse/",
        views.sales_reverse_shipment,
        name="sales_reverse_shipment",
    ),
    # Finance
    path("finance/", views.finance_dashboard, name="finance"),
    path("finance/kpis/", views.finance_kpis, name="finance_kpis"),
    path("finance/ledger/", views.finance_ledger, name="finance_ledger"),
    path("finance/ledger/create-account/", views.finance_account_create, name="finance_account_create"),
    path("finance/journal/", views.finance_journal, name="finance_journal"),
    path("finance/journal/create/", views.finance_journal_create, name="finance_journal_create"),
    path("finance/journal/<int:pk>/post/", views.finance_journal_post, name="finance_journal_post"),
    path("finance/periods/", views.finance_periods, name="finance_periods"),
    path("finance/periods/<int:pk>/close/", views.finance_period_close, name="finance_period_close"),
    path("finance/bank-recon/", views.finance_bank_recon, name="finance_bank_recon"),
    path("finance/invoices/", views.finance_invoices, name="finance_invoices"),
    path("finance/invoices/create/", views.finance_invoice_create, name="finance_invoice_create"),
    path(
        "finance/invoices/<int:pk>/",
        views.finance_invoice_detail,
        name="finance_invoice_detail",
    ),
    path(
        "finance/invoices/<int:pk>/issue/",
        views.finance_invoice_issue,
        name="finance_invoice_issue",
    ),
    path(
        "finance/invoices/<int:pk>/pdf/",
        views.finance_invoice_pdf,
        name="finance_invoice_pdf",
    ),
    path(
        "finance/invoices/<int:pk>/void/",
        views.finance_invoice_cancel,
        name="finance_invoice_cancel",
    ),
    path(
        "finance/invoices/<int:pk>/mark-paid/",
        views.finance_invoice_mark_paid,
        name="finance_invoice_mark_paid",
    ),
    path("finance/ar/", views.finance_ar, name="finance_ar"),
    path("finance/payment/", views.finance_payment_entry, name="finance_payment_entry"),
    path("finance/ap/", views.finance_ap, name="finance_ap"),
    path("finance/pricing/", views.finance_pricing, name="finance_pricing"),
    path(
        "finance/pricing/customer/create/",
        views.finance_pricing_customer_create,
        name="finance_pricing_customer_create",
    ),
    path(
        "finance/pricing/vendor/create/",
        views.finance_pricing_vendor_create,
        name="finance_pricing_vendor_create",
    ),
    path("finance/cost-master/", views.finance_cost_master, name="finance_cost_master"),
    path(
        "finance/margin-trends/",
        views.finance_margin_trends,
        name="finance_margin_trends",
    ),
    path(
        "finance/rm-lot-costs/",
        views.finance_rm_lot_costs,
        name="finance_rm_lot_costs",
    ),
    path("finance/reports/", views.finance_reports, name="finance_reports"),
    path("finance/pl-actual/", views.finance_pl_actual, name="finance_pl_actual"),
    path(
        "finance/pl-proforma/",
        views.finance_pl_proforma,
        name="finance_pl_proforma",
    ),
    # Production
    path("production/", views.production_batches, name="production"),
    path(
        "production/create-batch/",
        views.production_create_batch,
        name="production_create_batch",
    ),
    path(
        "production/<int:pk>/",
        views.production_batch_detail,
        name="production_batch_detail",
    ),
    path(
        "production/<int:pk>/pdf/",
        views.production_batch_pdf,
        name="production_batch_pdf",
    ),
    path(
        "production/<int:pk>/adjust/",
        views.production_adjust_batch,
        name="production_adjust_batch",
    ),
    path(
        "production/<int:pk>/close/",
        views.production_close_batch,
        name="production_close_batch",
    ),
    path(
        "production/<int:pk>/reverse/",
        views.production_reverse_batch,
        name="production_reverse_batch",
    ),
    # Quality
    path("quality/", views.quality_vendors, name="quality"),
    path("quality/vendors/create/", views.quality_create_vendor, name="quality_create_vendor"),
    path(
        "quality/vendors/<int:pk>/",
        views.quality_vendor_detail,
        name="quality_vendor_detail",
    ),
    path(
        "quality/vendors/<int:pk>/documents/<int:doc_pk>/download/",
        views.quality_vendor_document_download,
        name="quality_vendor_document_download",
    ),
    path(
        "quality/lot-tracking/",
        views.quality_lot_tracking,
        name="quality_lot_tracking",
    ),
    path(
        "quality/coa-library/",
        views.quality_coa_library,
        name="quality_coa_library",
    ),
    path(
        "quality/coa-library/master/<int:pk>/pdf/",
        views.quality_coa_pdf,
        name="quality_coa_pdf",
    ),
    path(
        "quality/coa-library/customer/<int:pk>/pdf/",
        views.quality_coa_customer_pdf,
        name="quality_coa_customer_pdf",
    ),
    path(
        "quality/finished-goods/",
        views.quality_finished_goods,
        name="quality_finished_goods",
    ),
    path(
        "quality/finished-goods/create/",
        views.quality_create_finished_good,
        name="quality_create_finished_good",
    ),
    path(
        "quality/finished-goods/unlink/",
        views.quality_unlink_finished_good,
        name="quality_unlink_finished_good",
    ),
    path(
        "quality/finished-goods/<int:pk>/coa-tests/",
        views.quality_item_coa_test_lines,
        name="quality_item_coa_test_lines",
    ),
    path(
        "quality/finished-goods/<int:pk>/",
        views.quality_finished_good_detail,
        name="quality_finished_good_detail",
    ),
    path(
        "quality/rd-formulas/",
        views.quality_rd_formulas,
        name="quality_rd_formulas",
    ),
    path(
        "quality/rd-formulas/new/",
        views.quality_rd_formula_create,
        name="quality_rd_formula_create",
    ),
    path(
        "quality/rd-formulas/<int:pk>/",
        views.quality_rd_formula_detail,
        name="quality_rd_formula_detail",
    ),
    path("quality/ccps/", views.quality_ccps, name="quality_ccps"),
]
