from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from erp_core.forms import (
    AccountForm,
    CostMasterForm,
    CustomerPricingStandaloneForm,
    InvoiceStatusForm,
    VendorPricingForm,
)
from erp_core.mixins import SlurpLoginRequiredMixin
from erp_core.models import Account, CostMaster, CustomerPricing, Invoice, VendorPricing
from erp_core.services.finance import get_aging_report, get_chart_of_accounts


class FinanceDashboardView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/finance/dashboard.html'
    extra_context = {'module': 'finance'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tab'] = self.request.GET.get('tab', 'gl')
        ctx['accounts'] = get_chart_of_accounts()
        ctx['invoices'] = Invoice.objects.select_related('sales_order__customer').all()
        ctx['cost_master'] = CostMaster.objects.all()
        ctx['vendor_pricing'] = VendorPricing.objects.select_related('item').filter(is_active=True)
        ctx['customer_pricing'] = CustomerPricing.objects.select_related('customer', 'item').filter(is_active=True)
        ctx['aging'] = get_aging_report()
        return ctx


class AccountCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/finance/account_form.html', {
            'module': 'finance', 'form': AccountForm(), 'title': 'Create Account',
        })

    def post(self, request):
        form = AccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created.')
            return redirect(f"{reverse('finance_dashboard')}?tab=gl")
        return render(request, 'erp/finance/account_form.html', {
            'module': 'finance', 'form': form, 'title': 'Create Account',
        })


class InvoiceDetailView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/finance/invoice_detail.html'
    extra_context = {'module': 'finance'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['invoice'] = get_object_or_404(
            Invoice.objects.prefetch_related('items'), pk=self.kwargs['pk']
        )
        ctx['status_form'] = InvoiceStatusForm(initial={'status': ctx['invoice'].status})
        return ctx


class InvoiceStatusUpdateView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        form = InvoiceStatusForm(request.POST)
        if form.is_valid():
            invoice.status = form.cleaned_data['status']
            invoice.save()
            messages.success(request, 'Invoice status updated.')
        return redirect('invoice_detail', pk=pk)


class CostMasterCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/finance/cost_master_form.html', {
            'module': 'finance', 'form': CostMasterForm(), 'title': 'Create Cost Master Entry',
        })

    def post(self, request):
        form = CostMasterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cost master entry created.')
            return redirect(f"{reverse('finance_dashboard')}?tab=cost")
        return render(request, 'erp/finance/cost_master_form.html', {
            'module': 'finance', 'form': form, 'title': 'Create Cost Master Entry',
        })


class VendorPricingCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/finance/vendor_pricing_form.html', {
            'module': 'finance', 'form': VendorPricingForm(), 'title': 'Create Vendor Pricing',
        })

    def post(self, request):
        form = VendorPricingForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendor pricing created.')
            return redirect(f"{reverse('finance_dashboard')}?tab=pricing")
        return render(request, 'erp/finance/vendor_pricing_form.html', {
            'module': 'finance', 'form': form, 'title': 'Create Vendor Pricing',
        })


class CustomerPricingCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/finance/customer_pricing_form.html', {
            'module': 'finance', 'form': CustomerPricingStandaloneForm(), 'title': 'Create Customer Pricing',
        })

    def post(self, request):
        form = CustomerPricingStandaloneForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer pricing created.')
            return redirect(f"{reverse('finance_dashboard')}?tab=pricing")
        return render(request, 'erp/finance/customer_pricing_form.html', {
            'module': 'finance', 'form': form, 'title': 'Create Customer Pricing',
        })


class AgingReportView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/finance/aging_report.html'
    extra_context = {'module': 'finance'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['aging'] = get_aging_report()
        return ctx
