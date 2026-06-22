from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from erp_core.forms import BatchInputFormSet, CloseBatchForm, ProductionBatchForm
from erp_core.mixins import SlurpLoginRequiredMixin
from erp_core.models import ProductionBatch
from erp_core.services.inventory import WorkflowError
from erp_core.services.production import (
    close_production_batch,
    create_production_batch,
    reverse_production_batch,
)


class ProductionDashboardView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/production/dashboard.html'
    extra_context = {'module': 'production'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['batches'] = ProductionBatch.objects.select_related(
            'finished_good_item'
        ).prefetch_related('inputs__lot', 'outputs__lot').all()
        return ctx


class ProductionBatchCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/production/batch_form.html', {
            'module': 'production',
            'form': ProductionBatchForm(),
            'formset': BatchInputFormSet(),
        })

    def post(self, request):
        form = ProductionBatchForm(request.POST)
        formset = BatchInputFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            inputs = [
                {'lot_id': f.cleaned_data['lot'].id, 'quantity_used': f.cleaned_data['quantity_used']}
                for f in formset if f.cleaned_data and f.cleaned_data.get('lot')
            ]
            if not inputs:
                messages.error(request, 'Add at least one input lot.')
            else:
                try:
                    batch = create_production_batch(
                        batch_type=form.cleaned_data['batch_type'],
                        finished_good_item=form.cleaned_data['finished_good_item'],
                        quantity_produced=form.cleaned_data['quantity_produced'],
                        inputs_data=inputs,
                        notes=form.cleaned_data.get('notes', ''),
                    )
                    messages.success(request, f'Batch {batch.batch_number} created.')
                    return redirect('production_batch_detail', pk=batch.pk)
                except WorkflowError as e:
                    messages.error(request, str(e))
        return render(request, 'erp/production/batch_form.html', {
            'module': 'production', 'form': form, 'formset': formset,
        })


class ProductionBatchDetailView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/production/batch_detail.html'
    extra_context = {'module': 'production'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['batch'] = get_object_or_404(
            ProductionBatch.objects.prefetch_related('inputs__lot__item', 'outputs__lot__item'),
            pk=self.kwargs['pk'],
        )
        ctx['close_form'] = CloseBatchForm(initial={
            'quantity_actual': ctx['batch'].quantity_produced,
        })
        return ctx


class ProductionBatchCloseView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        batch = get_object_or_404(ProductionBatch, pk=pk)
        form = CloseBatchForm(request.POST)
        if form.is_valid():
            try:
                close_production_batch(
                    batch,
                    quantity_actual=form.cleaned_data['quantity_actual'],
                    variance=form.cleaned_data.get('variance') or 0,
                    wastes=form.cleaned_data.get('wastes') or 0,
                    spills=form.cleaned_data.get('spills') or 0,
                )
                messages.success(request, f'Batch {batch.batch_number} closed.')
            except WorkflowError as e:
                messages.error(request, str(e))
        return redirect('production_batch_detail', pk=pk)


class ProductionBatchReverseView(SlurpLoginRequiredMixin, View):
    def post(self, request, pk):
        batch = get_object_or_404(ProductionBatch, pk=pk)
        try:
            reverse_production_batch(batch)
            messages.success(request, 'Batch reversed (UNFK).')
            return redirect('production_dashboard')
        except WorkflowError as e:
            messages.error(request, str(e))
            return redirect('production_batch_detail', pk=pk)
