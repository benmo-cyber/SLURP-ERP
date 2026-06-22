"""Example document contexts and PDF rendering — matches legacy WWI ERP templates."""
from pathlib import Path

from erp_core.batch_ticket_pdf_html import (
    BATCH_TICKET_UPDATED,
    CONFIDENTIALITY_FOOTER,
)
from erp_core.html_pdf_common import html_string_to_pdf_bytes
from erp_core.pdf_generator import get_batch_ticket_logo_base64_cached, get_logo_base64_cached


def _jinja_env(template_folder: str):
    from jinja2 import Environment, FileSystemLoader

    template_dir = Path(__file__).resolve().parent / 'templates' / template_folder
    return Environment(loader=FileSystemLoader(str(template_dir)))


def render_template_pdf(template_folder: str, template_name: str, context: dict, log_label: str) -> bytes | None:
    env = _jinja_env(template_folder)
    html_string = env.get_template(template_name).render(**context)
    return html_string_to_pdf_bytes(html_string, log_label=log_label)


def example_batch_ticket_context() -> dict:
    """Context shaped like batch_ticket_pdf_html._build_batch_ticket_context output."""
    return {
        'product_id': '2847',
        'sku': 'ORG-VAN-EX-32',
        'batch_number': 'BT-2026-0042',
        'campaign_lot_code': 'CL-0618-A',
        'batch_size': '2500 lbs',
        'pack_size': '55 lbs',
        'prod_date': '06/18/2026',
        'pick_rows': [
            {
                'sku': 'RM-SUG-ORG-001',
                'vendor': 'Florida Crystals',
                'vendor_lot': 'FC-88421',
                'qty': '1875',
                'uom': 'lbs',
                'pick_init': '',
                'prod_init': '',
                'wildwood_lot': '1ORG001',
            },
            {
                'sku': 'RM-VAN-BEAN-002',
                'vendor': 'Symrise',
                'vendor_lot': 'SY-442901',
                'qty': '625',
                'uom': 'lbs',
                'pick_init': '',
                'prod_init': '',
                'wildwood_lot': '1VAN003',
            },
            {'sku': '', 'vendor': '', 'vendor_lot': '', 'qty': '', 'uom': '', 'pick_init': '', 'prod_init': '', 'wildwood_lot': ''},
        ],
        'pack_rows': [
            {'packaging': '55 lb steel drum', 'lot': 'PKG-DRUM-55', 'qty': '45 EA', 'pick_init': '', 'pack_init': '', 'amount_unused': '+2'},
            {'packaging': 'Drum liner', 'lot': 'PKG-LIN-55', 'qty': '45 EA', 'pick_init': '', 'pack_init': '', 'amount_unused': ''},
            {'packaging': '', 'lot': '', 'qty': '', 'pick_init': '', 'pack_init': '', 'amount_unused': ''},
        ],
        'mixing_steps': [
            'Weigh all raw materials per formula. Verify lot numbers against pick list.',
            'Add sugar to mixer; run 5 min at low speed.',
            'Add vanilla extract slowly; mix 10 min until homogeneous.',
            'Sample for QC (moisture, organoleptic). Hold until QC approval.',
            'Transfer to pack-off line. Label drums with batch number and lot code.',
            'Record yield, waste, and spill on page 2.',
        ],
        'ccp_question': 'Has 20 mesh screen been inspected and installed properly?',
        'qc_info': {},
        'yield_val': '2475 lbs',
        'loss_val': '-25 lbs',
        'spill_val': '0 lbs',
        'waste_val': '0 lbs',
        'confidentiality': CONFIDENTIALITY_FOOTER,
        'batch_ticket_updated': BATCH_TICKET_UPDATED,
        'logo_base64': get_logo_base64_cached(),
    }


def example_packing_list_context() -> dict:
    """Context shaped like packing_list_pdf_html._build_packing_list_context output."""
    ship_to_lines = [
        'Acme Food Co.',
        'Receiving Dept.',
        '1200 Industrial Blvd',
        'St. Louis, MO 63101',
    ]
    bill_to_lines = [
        'Acme Food Co.',
        'Accounts Payable',
        '500 Commerce Dr, Suite 200',
        'St. Louis, MO 63102',
    ]
    return {
        'so_number': 'SO-1024',
        'ship_to_text': '\n'.join(ship_to_lines),
        'bill_to_text': '\n'.join(bill_to_lines),
        'ship_to_lines': ship_to_lines,
        'bill_to_lines': bill_to_lines,
        'date_str': '2026-06-18',
        'order_date_str': '2026-06-10',
        'ship_date_str': '2026-06-18',
        'po_ref': 'PO-88421',
        'po_so_str': 'PO-88421 / SO-1024',
        'dimensions': '—',
        'pieces': '2',
        'carrier': 'FedEx Freight',
        'tracking_number': '7894561230',
        'combined_note': '',
        'piece_dimension_rows': [
            {'piece_num': 1, 'dimensions': '48" x 40" x 48"', 'weight': '1210 lbs'},
            {'piece_num': 2, 'dimensions': '48" x 40" x 36"', 'weight': '890 lbs'},
        ],
        'line_items': [
            {
                'sku': 'ORG-VAN-EX-32',
                'description': 'Organic Vanilla Extract 32-fold',
                'quantity': '2000 lbs',
                'lots': '1ORG042 (1500 lbs); 1ORG043 (500 lbs)',
            },
            {
                'sku': 'NAT-ALM-EX-2X',
                'description': 'Natural Almond Extract 2x',
                'quantity': '600 lbs',
                'lots': '1ALM018 (600 lbs)',
            },
        ],
        'logo_base64': get_batch_ticket_logo_base64_cached(),
    }


def example_invoice_context() -> dict:
    """Context shaped like invoice_pdf_html._build_invoice_context output."""
    return {
        'invoice_number': 'INV-2026-0156',
        'invoice_date': '06/18/2026',
        'bill_to_html': 'Acme Food Co.<br/>Accounts Payable<br/>500 Commerce Dr, Suite 200<br/>St. Louis, MO 63102',
        'ship_to_html': 'Acme Food Co.<br/>Receiving Dept.<br/>1200 Industrial Blvd<br/>St. Louis, MO 63101',
        'comments_text': 'Deliver before 2 PM. Call receiving at ext. 442.',
        'cust_ref': 'PO-88421',
        'po_num': 'PO-88421',
        'so_num': 'SO-1024',
        'shipped_via': 'FedEx Freight 7894561230',
        'payment_terms': 'Net 30',
        'line_items': [
            {
                'qty': '2000 lbs',
                'description': 'Organic Vanilla Extract 32-fold',
                'unit_price': '$42.50',
                'total': '$85,000.00',
            },
            {
                'qty': '600 lbs',
                'description': 'Natural Almond Extract 2x',
                'unit_price': '$18.75',
                'total': '$11,250.00',
            },
        ],
        'subtotal': '$96,250.00',
        'tax': '$0.00',
        'shipping': '$450.00',
        'total_due': '$96,700.00',
        'logo_base64': get_batch_ticket_logo_base64_cached(),
    }


def generate_example_batch_ticket_pdf() -> bytes | None:
    return render_template_pdf(
        'batch_ticket', 'batch_ticket.html', example_batch_ticket_context(), 'Batch ticket example',
    )


def generate_example_packing_list_pdf() -> bytes | None:
    return render_template_pdf(
        'packing_list', 'packing_list.html', example_packing_list_context(), 'Packing list example',
    )


def generate_example_invoice_pdf() -> bytes | None:
    return render_template_pdf(
        'invoice', 'invoice.html', example_invoice_context(), 'Invoice example',
    )
