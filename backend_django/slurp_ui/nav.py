"""Sidebar / header navigation — mirrors React page shells."""

MAIN_TABS = [
    {"id": "inventory", "label": "Inventory", "url_name": "slurp_ui:inventory"},
    {"id": "finance", "label": "Finance", "url_name": "slurp_ui:finance"},
    {"id": "production", "label": "Production", "url_name": "slurp_ui:production"},
    {"id": "quality", "label": "Quality", "url_name": "slurp_ui:quality"},
    {"id": "sales", "label": "Sales", "url_name": "slurp_ui:sales"},
]

INVENTORY_NAV = [
    {
        "label": "Stock",
        "items": [
            {"id": "inventory", "label": "Inventory Table", "url_name": "slurp_ui:inventory"},
            {"id": "counts", "label": "Physical Counts", "url_name": "slurp_ui:inventory_counts"},
            {"id": "holds", "label": "On-hold log", "url_name": "slurp_ui:inventory_holds"},
        ],
    },
    {
        "label": "Items",
        "items": [{"id": "items", "label": "Items Management", "url_name": "slurp_ui:inventory_items"}],
    },
    {
        "label": "Purchasing",
        "items": [
            {
                "id": "purchase-orders",
                "label": "Purchase Orders",
                "url_name": "slurp_ui:inventory_purchase_orders",
            },
        ],
    },
    {
        "label": "Activity",
        "items": [
            {"id": "material-activity", "label": "Material activity", "url_name": "slurp_ui:inventory_material_activity"},
            {"id": "logs", "label": "Logs", "url_name": "slurp_ui:inventory_logs"},
        ],
    },
]

SALES_NAV = [
    {
        "label": "Customers",
        "items": [
            {"id": "customers", "label": "All Customers", "url_name": "slurp_ui:sales"},
            {"id": "customers-manage", "label": "Add / Edit Master", "url_name": "slurp_ui:sales_customers"},
        ],
    },
    {
        "label": "Fulfillment",
        "items": [
            {"id": "orders", "label": "Order Workqueue", "url_name": "slurp_ui:sales_orders"},
            {"id": "order-archive", "label": "Order Archive", "url_name": "slurp_ui:sales_order_archive"},
            {"id": "rmas", "label": "RMAs", "url_name": "slurp_ui:sales_rma_list"},
        ],
    },
    {
        "label": "Planning",
        "items": [
            {"id": "calendar", "label": "Ops Calendar", "url_name": "slurp_ui:sales_calendar"},
            {"id": "kpis", "label": "Shipping KPIs", "url_name": "slurp_ui:sales_kpis"},
        ],
    },
]

FINANCE_NAV = [
    {
        "label": "Home",
        "items": [
            {"id": "dashboard", "label": "Finance home", "url_name": "slurp_ui:finance"},
        ],
    },
    {
        "label": "Invoicing",
        "items": [
            {"id": "invoicing", "label": "Invoices & AR", "url_name": "slurp_ui:finance_invoices"},
        ],
    },
    {
        "label": "Payables",
        "items": [{"id": "ap", "label": "Accounts Payable", "url_name": "slurp_ui:finance_ap"}],
    },
    {
        "label": "Accounting",
        "items": [
            {"id": "ledger", "label": "General Ledger", "url_name": "slurp_ui:finance_ledger"},
            {"id": "journal", "label": "Journal Entries", "url_name": "slurp_ui:finance_journal"},
            {"id": "periods", "label": "Fiscal Periods", "url_name": "slurp_ui:finance_periods"},
            {
                "id": "bank-recon",
                "label": "Bank Reconciliation",
                "url_name": "slurp_ui:finance_bank_recon",
            },
        ],
    },
    {
        "label": "Cost",
        "items": [
            {"id": "costing", "label": "Costing", "url_name": "slurp_ui:finance_costing"},
        ],
    },
    {
        "label": "Reports",
        "items": [
            {"id": "reports", "label": "Financial Reports", "url_name": "slurp_ui:finance_reports"},
        ],
    },
]

PRODUCTION_NAV = [
    {
        "label": "Production",
        "items": [
            {"id": "batches", "label": "Batch Tickets", "url_name": "slurp_ui:production"},
            {"id": "rework", "label": "Rework", "url_name": "slurp_ui:production_rework"},
            {"id": "archive", "label": "Batch Archive", "url_name": "slurp_ui:production_archive"},
            {"id": "repacks", "label": "Repacks", "url_name": "slurp_ui:production_repacks"},
            {
                "id": "repack-archive",
                "label": "Repack Archive",
                "url_name": "slurp_ui:production_repack_archive",
            },
        ],
    },
]

QUALITY_NAV = [
    {
        "label": "Vendors",
        "items": [{"id": "vendors", "label": "Vendor Approval", "url_name": "slurp_ui:quality"}],
    },
    {
        "label": "Tracking",
        "items": [
            {
                "id": "lot-tracking",
                "label": "Lot Tracking",
                "url_name": "slurp_ui:quality_lot_tracking",
            },
            {"id": "coa-library", "label": "COA library", "url_name": "slurp_ui:quality_coa_library"},
        ],
    },
    {
        "label": "Products",
        "items": [
            {
                "id": "finished-goods",
                "label": "FPS",
                "url_name": "slurp_ui:quality_finished_goods",
            },
            {
                "id": "coa-test-catalog",
                "label": "COA / micro catalog",
                "url_name": "slurp_ui:quality_coa_test_catalog",
            },
            {
                "id": "rd-formulas",
                "label": "R&D Formulas",
                "url_name": "slurp_ui:quality_rd_formulas",
            },
            {"id": "ccps", "label": "Critical Control Points", "url_name": "slurp_ui:quality_ccps"},
        ],
    },
]
