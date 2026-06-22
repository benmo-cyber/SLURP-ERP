from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from erp_core.forms import (
    FPSForm,
    FinishedGoodForm,
    FormulaItemFormSet,
    SupplierDocumentForm,
    TemporaryExceptionForm,
    VendorForm,
)
from erp_core.mixins import SlurpLoginRequiredMixin
from erp_core.models import (
    FinishedProductSpecification,
    Formula,
    FormulaItem,
    Item,
    Lot,
    ProductionBatch,
    SupplierDocument,
    SupplierSurvey,
    TemporaryException,
    Vendor,
    VendorHistory,
)
from erp_core.services.inventory import WorkflowError, create_item_with_cost_master


class QualityDashboardView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/quality/dashboard.html'
    extra_context = {'module': 'quality'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tab'] = self.request.GET.get('tab', 'vendors')
        ctx['vendors'] = Vendor.objects.all()
        ctx['lots'] = Lot.objects.select_related('item').order_by('-received_date')[:100]
        ctx['finished_goods'] = Item.objects.filter(item_type='finished_good').select_related('formula', 'fps')
        return ctx


class VendorCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/quality/vendor_form.html', {
            'module': 'quality', 'form': VendorForm(), 'title': 'Create Vendor',
        })

    def post(self, request):
        form = VendorForm(request.POST)
        if form.is_valid():
            vendor = form.save()
            SupplierSurvey.objects.get_or_create(vendor=vendor)
            messages.success(request, f'Vendor {vendor.name} created.')
            return redirect('vendor_detail', pk=vendor.pk)
        return render(request, 'erp/quality/vendor_form.html', {
            'module': 'quality', 'form': form, 'title': 'Create Vendor',
        })


class VendorDetailView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/quality/vendor_detail.html'
    extra_context = {'module': 'quality'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vendor = get_object_or_404(
            Vendor.objects.prefetch_related('documents', 'history', 'exceptions'),
            pk=self.kwargs['pk'],
        )
        ctx['vendor'] = vendor
        ctx['survey'] = getattr(vendor, 'survey', None)
        ctx['tab'] = self.request.GET.get('tab', 'overview')
        ctx['exception_form'] = TemporaryExceptionForm()
        ctx['document_form'] = SupplierDocumentForm()
        return ctx


class VendorApproveView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        vendor = get_object_or_404(Vendor, pk=pk)
        vendor.approval_status = 'approved'
        vendor.approved_date = timezone.now()
        vendor.approved_by = request.user.username
        vendor.save()
        VendorHistory.objects.create(
            vendor=vendor,
            history_type='approval_change',
            description='Vendor approved',
            created_by=request.user.username,
        )
        messages.success(request, f'{vendor.name} approved.')
        return redirect('vendor_detail', pk=pk)


class TemporaryExceptionCreateView(SlurpLoginRequiredMixin, View):
    def post(self, request, vendor_pk):
        vendor = get_object_or_404(Vendor, pk=vendor_pk)
        form = TemporaryExceptionForm(request.POST)
        if form.is_valid():
            exc = form.save(commit=False)
            exc.vendor = vendor
            exc.requested_by = request.user.username
            exc.save()
            messages.success(request, 'Temporary exception submitted.')
        else:
            messages.error(request, 'Could not save exception.')
        return redirect(f"{reverse('vendor_detail', kwargs={'pk': vendor_pk})}?tab=exceptions")


class TemporaryExceptionApproveView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        exc = get_object_or_404(TemporaryException, pk=pk)
        exc.status = 'approved'
        exc.approved_by = request.user.username
        exc.approved_date = timezone.now()
        exc.save()
        messages.success(request, 'Exception approved.')
        return redirect(f"{reverse('vendor_detail', kwargs={'pk': exc.vendor_id})}?tab=exceptions")


class SupplierDocumentUploadView(SlurpLoginRequiredMixin, View):
    def post(self, request, vendor_pk):
        vendor = get_object_or_404(Vendor, pk=vendor_pk)
        form = SupplierDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.vendor = vendor
            doc.uploaded_by = request.user.username
            uploaded = request.FILES.get('file_upload')
            if uploaded:
                doc.file = uploaded.read()
                doc.file_name = uploaded.name
                doc.file_size = uploaded.size
                doc.mime_type = uploaded.content_type or 'application/octet-stream'
            doc.save()
            messages.success(request, 'Document uploaded.')
        else:
            messages.error(request, 'Upload failed.')
        return redirect(f"{reverse('vendor_detail', kwargs={'pk': vendor_pk})}?tab=documents")


class FinishedGoodCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/quality/finished_good_form.html', {
            'module': 'quality',
            'item_form': FinishedGoodForm(),
            'formula_formset': FormulaItemFormSet(),
            'fps_form': FPSForm(),
        })

    def post(self, request):
        item_form = FinishedGoodForm(request.POST)
        formula_formset = FormulaItemFormSet(request.POST)
        fps_form = FPSForm(request.POST)
        if item_form.is_valid() and formula_formset.is_valid():
            try:
                item = create_item_with_cost_master({
                    'sku': item_form.cleaned_data['sku'],
                    'name': item_form.cleaned_data['name'],
                    'item_type': 'finished_good',
                    'unit_of_measure': item_form.cleaned_data['unit_of_measure'],
                    'vendor': item_form.cleaned_data.get('vendor') or None,
                    'on_order': 0,
                })
                formula = Formula.objects.create(finished_good=item)
                for f in formula_formset:
                    if f.cleaned_data and f.cleaned_data.get('item'):
                        FormulaItem.objects.create(
                            formula=formula,
                            item=f.cleaned_data['item'],
                            percentage=f.cleaned_data['percentage'],
                        )
                if fps_form.is_valid():
                    fps = fps_form.save(commit=False)
                    fps.item = item
                    fps.save()
                messages.success(request, f'Finished good {item.name} created.')
                return redirect(f"{reverse('quality_dashboard')}?tab=finished")
            except WorkflowError as e:
                messages.error(request, str(e))
        return render(request, 'erp/quality/finished_good_form.html', {
            'module': 'quality',
            'item_form': item_form,
            'formula_formset': formula_formset,
            'fps_form': fps_form,
        })


class LotTrackingView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/quality/lot_tracking.html'
    extra_context = {'module': 'quality'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lots'] = Lot.objects.select_related('item').order_by('-received_date')
        ctx['batches'] = ProductionBatch.objects.select_related('finished_good_item').order_by('-created_at')[:50]
        return ctx
