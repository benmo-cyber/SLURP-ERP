from django import forms
from django.forms import formset_factory, inlineformset_factory

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
    Item,
    Lot,
    ProductionBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    ShipToLocation,
    SupplierDocument,
    TemporaryException,
    Vendor,
    VendorPricing,
)


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'sku', 'name', 'description', 'item_type', 'unit_of_measure',
            'vendor', 'pack_size', 'price', 'approved_for_formulas',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class CheckInForm(forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.all())
    quantity = forms.FloatField(min_value=0.01)
    status = forms.ChoiceField(choices=Lot.STATUS_CHOICES, initial='accepted')
    vendor_lot_number = forms.CharField(required=False, max_length=100)
    po_number = forms.CharField(required=False, max_length=100)
    freight_actual = forms.FloatField(required=False)
    short_reason = forms.CharField(required=False, max_length=255)


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            'vendor_customer_name', 'expected_delivery_date', 'required_date',
            'shipping_terms', 'shipping_method', 'shipping_cost', 'discount',
            'coa_sds_email', 'tracking_number', 'carrier', 'notes',
        ]
        widgets = {
            'expected_delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'required_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class PurchaseOrderItemForm(forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.all())
    quantity_ordered = forms.FloatField(min_value=0.01)
    unit_price = forms.FloatField(required=False, min_value=0)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 1}))


PurchaseOrderItemFormSet = formset_factory(PurchaseOrderItemForm, extra=3, can_delete=True)


class ProductionBatchForm(forms.Form):
    batch_type = forms.ChoiceField(choices=ProductionBatch.BATCH_TYPE_CHOICES)
    finished_good_item = forms.ModelChoiceField(
        queryset=Item.objects.filter(item_type='finished_good')
    )
    quantity_produced = forms.FloatField(min_value=0.01)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class BatchInputForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.filter(status='accepted'))
    quantity_used = forms.FloatField(min_value=0.01)


BatchInputFormSet = formset_factory(BatchInputForm, extra=2)


class CloseBatchForm(forms.Form):
    quantity_actual = forms.FloatField(min_value=0)
    variance = forms.FloatField(initial=0, required=False)
    wastes = forms.FloatField(initial=0, required=False)
    spills = forms.FloatField(initial=0, required=False)


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'name', 'vendor_id', 'contact_name', 'email', 'phone', 'address',
            'risk_profile', 'risk_tier', 'notes',
            'gfsi_certified', 'fsma_compliant', 'ctpat_certified',
        ]
        widgets = {'address': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 2})}


class TemporaryExceptionForm(forms.ModelForm):
    class Meta:
        model = TemporaryException
        fields = [
            'material_commodity', 'country_of_origin', 'intended_use',
            'po_number', 'lot_number', 'justification', 'risk_summary', 'notes',
        ]
        widgets = {
            'intended_use': forms.Textarea(attrs={'rows': 2}),
            'justification': forms.Textarea(attrs={'rows': 2}),
        }


class SupplierDocumentForm(forms.ModelForm):
    file_upload = forms.FileField(required=True)

    class Meta:
        model = SupplierDocument
        fields = ['document_type', 'document_name', 'issue_date', 'expiration_date', 'notes']
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'expiration_date': forms.DateInput(attrs={'type': 'date'}),
        }


class FormulaForm(forms.ModelForm):
    class Meta:
        model = Formula
        fields = ['version', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}


class FormulaItemForm(forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.filter(item_type='raw_material'))
    percentage = forms.FloatField(min_value=0, max_value=100)


FormulaItemFormSet = formset_factory(FormulaItemForm, extra=3)


class FinishedGoodForm(forms.Form):
    sku = forms.CharField(max_length=255)
    name = forms.CharField(max_length=255)
    unit_of_measure = forms.ChoiceField(choices=Item.UNIT_CHOICES)
    vendor = forms.CharField(required=False, max_length=255)


class FPSForm(forms.ModelForm):
    class Meta:
        model = FinishedProductSpecification
        exclude = ['item', 'fps_pdf']
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 2}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'name', 'contact_name', 'email', 'phone', 'address', 'city',
            'state', 'zip_code', 'country', 'payment_terms', 'notes', 'is_active',
        ]
        widgets = {'address': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 2})}


class ShipToLocationForm(forms.ModelForm):
    class Meta:
        model = ShipToLocation
        fields = [
            'location_name', 'contact_name', 'email', 'phone', 'address',
            'city', 'state', 'zip_code', 'country', 'is_default', 'notes',
        ]


class CustomerContactForm(forms.ModelForm):
    class Meta:
        model = CustomerContact
        fields = [
            'first_name', 'last_name', 'title', 'email', 'phone',
            'mobile', 'is_primary', 'notes',
        ]


class SalesCallForm(forms.ModelForm):
    class Meta:
        model = SalesCall
        fields = [
            'contact', 'call_date', 'call_type', 'subject', 'notes',
            'follow_up_required', 'follow_up_date',
        ]
        widgets = {
            'call_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'follow_up_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if customer is not None:
            self.fields['contact'].queryset = CustomerContact.objects.filter(customer=customer)
            self.fields['contact'].required = False


class CustomerForecastForm(forms.ModelForm):
    class Meta:
        model = CustomerForecast
        fields = ['item', 'forecast_period', 'forecast_quantity', 'unit_of_measure', 'notes']


class CustomerPricingForm(forms.ModelForm):
    """Inline pricing on customer profile (customer set by view)."""
    class Meta:
        model = CustomerPricing
        fields = [
            'item', 'unit_price', 'unit_of_measure', 'effective_date',
            'expiry_date', 'is_active', 'notes',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class CustomerPricingStandaloneForm(forms.ModelForm):
    """Pricing form from Finance module."""
    class Meta:
        model = CustomerPricing
        fields = [
            'customer', 'item', 'unit_price', 'unit_of_measure', 'effective_date',
            'expiry_date', 'is_active', 'notes',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class SalesOrderForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.filter(is_active=True))
    customer_reference_number = forms.CharField(required=False, max_length=255)
    expected_ship_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class SalesOrderItemForm(forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.all())
    quantity_ordered = forms.FloatField(min_value=0.01)
    unit_price = forms.FloatField(required=False, min_value=0)


SalesOrderItemFormSet = formset_factory(SalesOrderItemForm, extra=2)


class CheckoutAllocationForm(forms.Form):
    sales_order_item_id = forms.IntegerField(widget=forms.HiddenInput)
    lot = forms.ModelChoiceField(queryset=Lot.objects.filter(status='accepted'))
    quantity = forms.FloatField(min_value=0.01)


class ShipOrderForm(forms.Form):
    ship_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    invoice_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['account_number', 'name', 'account_type', 'parent_account', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}


class InvoiceStatusForm(forms.Form):
    status = forms.ChoiceField(choices=[
        ('draft', 'Draft'), ('sent', 'Sent'), ('paid', 'Paid'),
        ('overdue', 'Overdue'), ('cancelled', 'Cancelled'),
    ])


class CostMasterForm(forms.ModelForm):
    class Meta:
        model = CostMaster
        fields = [
            'vendor_material', 'wwi_product_code', 'vendor', 'price_per_kg',
            'price_per_lb', 'incoterms', 'origin', 'hts_code', 'tariff',
            'freight_per_kg', 'landed_cost_per_kg', 'landed_cost_per_lb',
            'margin', 'selling_price_per_kg', 'lead_time', 'notes',
        ]
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}


class VendorPricingForm(forms.ModelForm):
    class Meta:
        model = VendorPricing
        fields = [
            'vendor_name', 'vendor_item_number', 'item', 'unit_price',
            'unit_of_measure', 'effective_date', 'expiry_date', 'is_active', 'notes',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class LotEditForm(forms.ModelForm):
    class Meta:
        model = Lot
        fields = ['quantity_remaining', 'status', 'expiration_date', 'short_reason']
        widgets = {'expiration_date': forms.DateTimeInput(attrs={'type': 'datetime-local'})}
