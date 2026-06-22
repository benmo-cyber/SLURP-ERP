"""Django admin registrations for SLURP ERP models."""

from django.contrib import admin

from erp_core.models import (
    Account,
    CostMaster,
    Customer,
    CustomerContact,
    CustomerForecast,
    CustomerPricing,
    FinishedProductSpecification,
    Formula,
    FormulaItem,
    Invoice,
    InvoiceItem,
    Item,
    Lot,
    ProductionBatch,
    ProductionBatchInput,
    ProductionBatchOutput,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    SalesOrderLot,
    ShipToLocation,
    SupplierDocument,
    SupplierSurvey,
    TemporaryException,
    Vendor,
    VendorHistory,
    VendorPricing,
)

admin.site.register(Item)
admin.site.register(Lot)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
admin.site.register(SalesOrder)
admin.site.register(SalesOrderItem)
admin.site.register(SalesOrderLot)
admin.site.register(ProductionBatch)
admin.site.register(ProductionBatchInput)
admin.site.register(ProductionBatchOutput)
admin.site.register(Formula)
admin.site.register(FormulaItem)
admin.site.register(Vendor)
admin.site.register(VendorHistory)
admin.site.register(SupplierSurvey)
admin.site.register(SupplierDocument)
admin.site.register(TemporaryException)
admin.site.register(CostMaster)
admin.site.register(Account)
admin.site.register(FinishedProductSpecification)
admin.site.register(Customer)
admin.site.register(ShipToLocation)
admin.site.register(CustomerContact)
admin.site.register(SalesCall)
admin.site.register(CustomerForecast)
admin.site.register(CustomerPricing)
admin.site.register(VendorPricing)
admin.site.register(Invoice)
admin.site.register(InvoiceItem)
