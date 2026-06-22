"""Printable example documents — legacy WWI ERP PDF templates."""
from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView

from erp_core.example_document_pdf import (
    generate_example_batch_ticket_pdf,
    generate_example_invoice_pdf,
    generate_example_packing_list_pdf,
)
from erp_core.mixins import SlurpLoginRequiredMixin


def _pdf_response(pdf_bytes: bytes | None, filename: str) -> HttpResponse:
    if not pdf_bytes:
        return HttpResponse('PDF generation failed.', status=500, content_type='text/plain')
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


class ExampleDocumentsIndexView(SlurpLoginRequiredMixin, TemplateView):
    template_name = 'erp/documents/index.html'


class ExampleBatchTicketView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return _pdf_response(generate_example_batch_ticket_pdf(), 'Batch_Ticket_BT-2026-0042.pdf')


class ExamplePackingListView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return _pdf_response(generate_example_packing_list_pdf(), 'Packing_List_SO-1024.pdf')


class ExampleInvoiceView(SlurpLoginRequiredMixin, View):
    def get(self, request):
        return _pdf_response(generate_example_invoice_pdf(), 'Invoice_INV-2026-0156.pdf')
