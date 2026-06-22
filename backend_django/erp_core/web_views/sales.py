from datetime import date, datetime

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from erp_core.forms import (
    CheckoutAllocationForm,
    CustomerContactForm,
    CustomerForecastForm,
    CustomerForm,
    CustomerPricingForm,
    SalesCallForm,
    SalesOrderForm,
    SalesOrderItemFormSet,
    ShipOrderForm,
    ShipToLocationForm,
)
from erp_core.mixins import SlurpLoginRequiredMixin
from erp_core.models import (
    Customer,
    CustomerContact,
    CustomerForecast,
    CustomerPricing,
    Lot,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    SalesOrderLot,
    ShipToLocation,
)
from erp_core.services.finance import get_calendar_events
from erp_core.services.inventory import WorkflowError
from erp_core.services.numbers import generate_customer_id
from erp_core.services.sales_orders import allocate_sales_order, create_sales_order, ship_sales_order


class SalesDashboardView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/sales/dashboard.html'
    extra_context = {'module': 'sales'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tab'] = self.request.GET.get('tab', 'crm')
        ctx['customers'] = Customer.objects.filter(is_active=True)
        ctx['sales_orders'] = SalesOrder.objects.select_related('customer').prefetch_related('items__item').all()
        today = date.today()
        start = today.replace(day=1)
        ctx['calendar_events'] = get_calendar_events(start, today.replace(day=28))
        return ctx


class CustomerCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/sales/customer_form.html', {
            'module': 'sales', 'form': CustomerForm(), 'title': 'Create Customer',
        })

    def post(self, request):
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.customer_id = generate_customer_id()
            customer.save()
            messages.success(request, f'Customer {customer.name} created.')
            return redirect('customer_detail', pk=customer.pk)
        return render(request, 'erp/sales/customer_form.html', {
            'module': 'sales', 'form': form, 'title': 'Create Customer',
        })


class CustomerDetailView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/sales/customer_detail.html'
    extra_context = {'module': 'sales'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = get_object_or_404(
            Customer.objects.prefetch_related(
                'ship_to_locations', 'contacts', 'sales_calls', 'forecasts', 'pricing__item'
            ),
            pk=self.kwargs['pk'],
        )
        ctx['customer'] = customer
        ctx['tab'] = self.request.GET.get('tab', 'overview')
        ctx['ship_to_form'] = ShipToLocationForm()
        ctx['contact_form'] = CustomerContactForm()
        ctx['sales_call_form'] = SalesCallForm(customer=customer)
        ctx['forecast_form'] = CustomerForecastForm()
        ctx['pricing_form'] = CustomerPricingForm()
        return ctx


class CustomerSubCreateView(SlurpLoginRequiredMixin, View):
    MODEL_MAP = {
        'ship-to': (ShipToLocation, ShipToLocationForm, 'ship_to_locations'),
        'contact': (CustomerContact, CustomerContactForm, 'contacts'),
        'sales-call': (SalesCall, SalesCallForm, 'sales_calls'),
        'forecast': (CustomerForecast, CustomerForecastForm, 'forecasts'),
        'pricing': (CustomerPricing, CustomerPricingForm, 'pricing'),
    }

    def post(self, request, customer_pk, sub_type):
        customer = get_object_or_404(Customer, pk=customer_pk)
        mapping = self.MODEL_MAP.get(sub_type)
        if not mapping:
            messages.error(request, 'Unknown form type.')
            return redirect('customer_detail', pk=customer_pk)
        model_cls, form_cls, _ = mapping
        if sub_type == 'sales-call':
            form = form_cls(request.POST, customer=customer)
        else:
            form = form_cls(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.customer = customer
            if sub_type == 'sales-call':
                obj.created_by = request.user.username
            if sub_type == 'forecast':
                obj.created_by = request.user.username
            obj.save()
            messages.success(request, 'Record saved.')
        else:
            messages.error(request, 'Could not save record. Check the form for errors.')
        tab_map = {
            'ship-to': 'ship-to', 'contact': 'contacts', 'sales-call': 'calls',
            'forecast': 'forecasts', 'pricing': 'pricing',
        }
        return redirect(f"{reverse('customer_detail', kwargs={'pk': customer_pk})}?tab={tab_map.get(sub_type, 'overview')}")


class SalesOrderCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/sales/sales_order_form.html', {
            'module': 'sales',
            'so_form': SalesOrderForm(),
            'formset': SalesOrderItemFormSet(),
        })

    def post(self, request):
        so_form = SalesOrderForm(request.POST)
        formset = SalesOrderItemFormSet(request.POST)
        if so_form.is_valid() and formset.is_valid():
            items_data = [
                f.cleaned_data for f in formset
                if f.cleaned_data and f.cleaned_data.get('item')
            ]
            if not items_data:
                messages.error(request, 'Add at least one line item.')
            else:
                fields = {'notes': so_form.cleaned_data.get('notes', '')}
                expected = so_form.cleaned_data.get('expected_ship_date')
                if expected:
                    from django.utils import timezone as tz
                    fields['expected_ship_date'] = tz.make_aware(
                        datetime.combine(expected, datetime.min.time())
                    )
                so = create_sales_order(
                    customer=so_form.cleaned_data['customer'],
                    customer_reference_number=so_form.cleaned_data.get('customer_reference_number', ''),
                    items_data=items_data,
                    **fields,
                )
                messages.success(request, f'Sales order {so.so_number} created.')
                return redirect('sales_order_checkout', pk=so.pk)
        return render(request, 'erp/sales/sales_order_form.html', {
            'module': 'sales', 'so_form': so_form, 'formset': formset,
        })


class SalesOrderCheckoutView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/sales/checkout.html'
    extra_context = {'module': 'sales'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        so = get_object_or_404(
            SalesOrder.objects.prefetch_related('items__item', 'items__allocated_lots__lot'),
            pk=self.kwargs['pk'],
        )
        ctx['sales_order'] = so
        ctx['ship_form'] = ShipOrderForm(initial={'ship_date': date.today(), 'invoice_date': date.today()})
        ctx['allocation_forms'] = []
        for so_item in so.items.all():
            lots = Lot.objects.filter(item=so_item.item, status='accepted', quantity_remaining__gt=0)
            ctx['allocation_forms'].append({
                'so_item': so_item,
                'lots': lots,
            })
        return ctx


class SalesOrderAllocateView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        so = get_object_or_404(SalesOrder, pk=pk)
        allocations = []
        for so_item in so.items.all():
            lot_id = request.POST.get(f'lot_{so_item.id}')
            qty = request.POST.get(f'qty_{so_item.id}')
            if lot_id and qty:
                allocations.append({
                    'item_id': so_item.item_id,
                    'lot_id': int(lot_id),
                    'quantity': float(qty),
                })
        if not allocations:
            messages.error(request, 'No allocations provided.')
            return redirect('sales_order_checkout', pk=pk)
        try:
            allocate_sales_order(so, allocations)
            messages.success(request, 'Lots allocated.')
        except WorkflowError as e:
            messages.error(request, str(e))
        return redirect('sales_order_checkout', pk=pk)


class SalesOrderShipView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        so = get_object_or_404(SalesOrder, pk=pk)
        form = ShipOrderForm(request.POST)
        if form.is_valid():
            try:
                _, invoice = ship_sales_order(
                    so,
                    ship_date=form.cleaned_data['ship_date'],
                    invoice_date=form.cleaned_data.get('invoice_date') or form.cleaned_data['ship_date'],
                )
                messages.success(request, f'Order shipped. Invoice {invoice.invoice_number} created.')
                return redirect('invoice_detail', pk=invoice.pk)
            except WorkflowError as e:
                messages.error(request, str(e))
        return redirect('sales_order_checkout', pk=pk)


class CalendarView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/sales/calendar.html'
    extra_context = {'module': 'sales'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        ctx['events'] = get_calendar_events(
            today.replace(day=1),
            today.replace(day=28),
        )
        return ctx
