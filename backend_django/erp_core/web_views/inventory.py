from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from erp_core.forms import (
    CheckInForm,
    ItemForm,
    LotEditForm,
    PurchaseOrderForm,
    PurchaseOrderItemFormSet,
)
from erp_core.mixins import SlurpLoginRequiredMixin
from erp_core.models import Item, Lot, PurchaseOrder
from erp_core.services.inventory import (
    WorkflowError,
    check_in_lot,
    create_item_with_cost_master,
    get_inventory_summary,
    reverse_check_in,
)
from erp_core.services.purchase_orders import (
    cancel_purchase_order,
    create_purchase_order,
    issue_purchase_order,
    receive_purchase_order,
    revise_purchase_order,
)


class InventoryDashboardView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/inventory/dashboard.html'
    extra_context = {'module': 'inventory'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tab'] = self.request.GET.get('tab', 'inventory')
        ctx['inventory'] = get_inventory_summary()
        ctx['items'] = Item.objects.all()
        ctx['purchase_orders'] = PurchaseOrder.objects.prefetch_related('items__item').all()
        return ctx


class ItemCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/inventory/item_form.html', {
            'module': 'inventory', 'form': ItemForm(), 'title': 'Create Item',
        })

    def post(self, request):
        form = ItemForm(request.POST)
        if form.is_valid():
            try:
                create_item_with_cost_master(form.cleaned_data)
                messages.success(request, 'Item created.')
                return redirect(f"{reverse('inventory_dashboard')}?tab=items")
            except WorkflowError as e:
                messages.error(request, str(e))
        return render(request, 'erp/inventory/item_form.html', {
            'module': 'inventory', 'form': form, 'title': 'Create Item',
        })


class ItemEditView(SlurpLoginRequiredMixin, View):
    def get(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        return render(request, 'erp/inventory/item_form.html', {
            'module': 'inventory', 'form': ItemForm(instance=item), 'title': 'Edit Item', 'item': item,
        })

    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        form = ItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item updated.')
            return redirect(f"{reverse('inventory_dashboard')}?tab=items")
        return render(request, 'erp/inventory/item_form.html', {
            'module': 'inventory', 'form': form, 'title': 'Edit Item', 'item': item,
        })


class CheckInView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/inventory/check_in.html', {
            'module': 'inventory', 'form': CheckInForm(),
        })

    def post(self, request):
        form = CheckInForm(request.POST)
        if form.is_valid():
            try:
                check_in_lot(
                    item=form.cleaned_data['item'],
                    quantity=form.cleaned_data['quantity'],
                    lot_status=form.cleaned_data['status'],
                    vendor_lot_number=form.cleaned_data.get('vendor_lot_number', ''),
                    po_number=form.cleaned_data.get('po_number', ''),
                    freight_actual=form.cleaned_data.get('freight_actual'),
                    short_reason=form.cleaned_data.get('short_reason', ''),
                )
                messages.success(request, 'Check-in completed.')
                return redirect('inventory_dashboard')
            except WorkflowError as e:
                messages.error(request, str(e))
        return render(request, 'erp/inventory/check_in.html', {
            'module': 'inventory', 'form': form,
        })


class ReverseCheckInView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        lots = [l for l in Lot.objects.select_related('item') if l.quantity_remaining >= l.quantity]
        return render(request, 'erp/inventory/reverse_check_in.html', {
            'module': 'inventory', 'lots': lots,
        })

    def post(self, request):
        lot = get_object_or_404(Lot, pk=request.POST.get('lot_id'))
        try:
            reverse_check_in(lot)
            messages.success(request, f'Check-in reversed for lot {lot.lot_number}.')
        except WorkflowError as e:
            messages.error(request, str(e))
        return redirect('inventory_dashboard')


class LotEditView(SlurpLoginRequiredMixin, View):
    def get(self, request, pk):
        lot = get_object_or_404(Lot, pk=pk)
        return render(request, 'erp/inventory/lot_edit.html', {
            'module': 'inventory', 'lot': lot, 'form': LotEditForm(instance=lot),
        })

    def post(self, request, pk):
        lot = get_object_or_404(Lot, pk=pk)
        form = LotEditForm(request.POST, instance=lot)
        if form.is_valid():
            form.save()
            messages.success(request, 'Lot updated.')
            return redirect('inventory_dashboard')
        return render(request, 'erp/inventory/lot_edit.html', {
            'module': 'inventory', 'lot': lot, 'form': form,
        })


class PurchaseOrderCreateView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'erp/inventory/po_form.html', {
            'module': 'inventory',
            'po_form': PurchaseOrderForm(),
            'formset': PurchaseOrderItemFormSet(),
        })

    def post(self, request):
        po_form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST)
        if po_form.is_valid() and formset.is_valid():
            items_data = [
                f.cleaned_data for f in formset
                if f.cleaned_data and not f.cleaned_data.get('DELETE') and f.cleaned_data.get('item')
            ]
            if not items_data:
                messages.error(request, 'Add at least one line item.')
            else:
                try:
                    create_purchase_order(
                        vendor_name=po_form.cleaned_data['vendor_customer_name'],
                        items_data=items_data,
                        expected_delivery_date=po_form.cleaned_data.get('expected_delivery_date'),
                        required_date=po_form.cleaned_data.get('required_date'),
                        shipping_terms=po_form.cleaned_data.get('shipping_terms') or '',
                        shipping_method=po_form.cleaned_data.get('shipping_method') or '',
                        shipping_cost=po_form.cleaned_data.get('shipping_cost') or 0,
                        discount=po_form.cleaned_data.get('discount') or 0,
                        coa_sds_email=po_form.cleaned_data.get('coa_sds_email') or '',
                        tracking_number=po_form.cleaned_data.get('tracking_number') or '',
                        carrier=po_form.cleaned_data.get('carrier') or '',
                        notes=po_form.cleaned_data.get('notes') or '',
                    )
                    messages.success(request, 'Purchase order created.')
                    return redirect(f"{reverse('inventory_dashboard')}?tab=pos")
                except WorkflowError as e:
                    messages.error(request, str(e))
        return render(request, 'erp/inventory/po_form.html', {
            'module': 'inventory', 'po_form': po_form, 'formset': formset,
        })


class PurchaseOrderDetailView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/inventory/po_detail.html'
    extra_context = {'module': 'inventory'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['po'] = get_object_or_404(
            PurchaseOrder.objects.prefetch_related('items__item'), pk=self.kwargs['pk']
        )
        return ctx


class PurchaseOrderActionView(SlurpLoginRequiredMixin, View):
    ACTIONS = {
        'issue': issue_purchase_order,
        'receive': receive_purchase_order,
        'cancel': cancel_purchase_order,
    }

    def post(self, request, pk, action):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        if action == 'revise':
            try:
                new_po = revise_purchase_order(po)
                messages.success(request, f'Revision {new_po.revision_number} created.')
                return redirect('po_detail', pk=new_po.pk)
            except WorkflowError as e:
                messages.error(request, str(e))
                return redirect('po_detail', pk=pk)
        handler = self.ACTIONS.get(action)
        if handler:
            try:
                handler(po)
                messages.success(request, f'PO {action}d successfully.')
            except WorkflowError as e:
                messages.error(request, str(e))
        return redirect('po_detail', pk=pk)
