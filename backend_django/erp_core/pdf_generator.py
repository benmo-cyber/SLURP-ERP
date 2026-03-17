"""
PDF generation for invoices, purchase orders, and sales orders
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether, Flowable, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from django.utils import timezone
from datetime import datetime
from pathlib import Path
import os
import shutil
import logging

logger = logging.getLogger(__name__)


class _FixedSizeImage(Flowable):
    """Flowable that draws an image at fixed size so layout uses our dimensions (avoids bad PNG metadata)."""
    def __init__(self, source, width, height):
        self._source = source  # path string or file-like (BytesIO)
        self._width = width
        self._height = height
    def wrap(self, availWidth, availHeight):
        return (self._width, self._height)
    def draw(self):
        try:
            if hasattr(self._source, 'seek'):
                self._source.seek(0)
            self.canv.drawImage(ImageReader(self._source), 0, 0, width=self._width, height=self._height, preserveAspectRatio=True)
        except Exception as e:
            logger.warning("Invoice logo draw failed: %s", e)


# Invoice template uses Arial 9pt / 20pt; register Arial if available so PDF matches template
_INVOICE_FONT_REGISTERED = False


def _register_invoice_fonts():
    """Register Arial + Arial-Bold for invoice PDF to match template. Fallback to Helvetica if not found."""
    global _INVOICE_FONT_REGISTERED
    if _INVOICE_FONT_REGISTERED:
        return
    _INVOICE_FONT_REGISTERED = True
    windir = os.environ.get('WINDIR', 'C:\\Windows')
    font_dir = os.path.join(windir, 'Fonts')
    for font_name, filename in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf')]:
        try:
            for path in [os.path.join(font_dir, filename), filename]:
                if os.path.isfile(path):
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    break
        except Exception:
            pass


def _get_po_logo_path():
    """Path to logo for purchase order PDF. Uses Django BASE_DIR so it works when the server runs."""
    try:
        from django.conf import settings
        base_dir = Path(settings.BASE_DIR)
    except Exception:
        base_dir = Path(__file__).resolve().parent.parent  # backend_django
    template_dir = base_dir / 'batch_ticket_template'
    for name in ['logo.png', 'Logo.png', 'Wildwood Ingredients Logo - Transparent Background.png']:
        p = template_dir / name
        if p.exists():
            return str(p.resolve())
    return None


def get_logo_path():
    """Get the path to the Wildwood Ingredients logo (same as SLURP header).
    Prefers frontend/public/logo.png so PDFs match the app header; then batch_ticket_template, Sensitive.
    """
    base = Path(__file__).resolve().parent.parent.parent  # WWI ERP project root
    backend = Path(__file__).resolve().parent.parent  # backend_django
    names = ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']
    # 1) frontend/public — same logo as SLURP header so it's visible from the frontend
    frontend_path = base / 'frontend' / 'public' / 'logo.png'
    if frontend_path.exists():
        return str(frontend_path)
    for name in names:
        p = base / 'frontend' / 'public' / name
        if p.exists():
            return str(p)
    # 2) batch_ticket_template
    template_dir = backend / 'batch_ticket_template'
    if template_dir.exists():
        for name in names:
            p = template_dir / name
            if p.exists():
                return str(p)
    # 3) Sensitive (production)
    sensitive = base / 'Sensitive'
    if sensitive.exists():
        for name in names:
            p = sensitive / name
            if p.exists():
                return str(p)
    return None


def get_batch_ticket_logo_path():
    """Return the logo path used by the batch ticket (batch_ticket_template, Sensitive, frontend/public).
    Use this for the PO so the PO shows the same Wildwood logo as the batch ticket."""
    # Same resolution order as batch_ticket_pdf so PO and batch ticket use the same image
    base = Path(__file__).resolve().parent.parent.parent
    backend = Path(__file__).resolve().parent.parent
    names = ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']
    for folder, check_names in [
        (backend / 'batch_ticket_template', names),
        (base / 'Sensitive', names),
        (base / 'frontend' / 'public', ['logo.png', 'Logo.png', 'Wildwood Ingredients Logo - Transparent Background.png']),
    ]:
        if folder.exists():
            for name in check_names:
                p = folder / name
                if p.exists():
                    return str(p)
    # Fallback to general get_logo_path (e.g. frontend/public only)
    p = get_logo_path()
    if p and os.path.exists(p):
        return p
    return None


def _ensure_po_logo_in_template_dir():
    """
    Ensure the Wildwood logo exists in batch_ticket_template so the PO can load it reliably.
    If the logo is in Sensitive or frontend/public, copy it to batch_ticket_template.
    Returns absolute path to logo file, or None.
    """
    base = Path(__file__).resolve().parent.parent.parent
    backend = Path(__file__).resolve().parent.parent
    template_dir = backend / 'batch_ticket_template'
    names = ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']
    # 1) Already in template folder — use it
    if template_dir.exists():
        for name in names:
            p = template_dir / name
            if p.exists():
                return str(p.resolve())
    # 2) Copy from Sensitive or frontend/public into template folder
    for folder in [base / 'Sensitive', base / 'frontend' / 'public']:
        if not folder.exists():
            continue
        for name in names:
            src = folder / name
            if src.exists():
                try:
                    template_dir.mkdir(parents=True, exist_ok=True)
                    dest = template_dir / name
                    shutil.copy2(str(src), str(dest))
                    return str(dest.resolve())
                except Exception:
                    return str(src.resolve())
    return None


def add_logo_header(story, logo_path=None):
    """Add logo in upper left corner"""
    if logo_path is None:
        logo_path = get_logo_path()
    
    if logo_path and os.path.exists(logo_path):
        try:
            # Create a table with logo on left and empty space on right
            logo_img = Image(logo_path, width=2*inch, height=0.75*inch)
            header_table = Table([[logo_img, '']], colWidths=[2.5*inch, 3.5*inch])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (0, 0), (0, 0), 0),
                ('TOPPADDING', (0, 0), (0, 0), 0),
                ('BOTTOMPADDING', (0, 0), (0, 0), 0),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 0.2*inch))
        except Exception as e:
            # If logo fails to load, just continue without it
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not load logo: {e}")


def _invoice_bill_to(invoice):
    """Bill-to from customer profile (customer on the sales order)."""
    so = getattr(invoice, 'sales_order', None)
    c = getattr(so, 'customer', None) if so else None
    if not c:
        return [], ''
    lines = [
        (getattr(c, 'name', None) or '').strip(),
        (getattr(c, 'address', None) or '').strip(),
        ', '.join(filter(None, [
            (getattr(c, 'city', None) or '').strip(),
            (getattr(c, 'state', None) or '').strip(),
            (getattr(c, 'zip_code', None) or '').strip(),
        ])).strip(),
        ('Phone: ' + (getattr(c, 'phone', None) or '').strip()) if getattr(c, 'phone', None) else '',
    ]
    return [l for l in lines if l], (getattr(c, 'payment_terms', None) or '').strip()


def _invoice_ship_to(invoice):
    """Ship-to from sales order (ship_to_location or legacy address)."""
    so = getattr(invoice, 'sales_order', None)
    if not so:
        return []
    loc = getattr(so, 'ship_to_location', None)
    if loc:
        lines = [
            (getattr(loc, 'location_name', None) or getattr(loc, 'contact_name', None) or '').strip(),
            (getattr(loc, 'address', None) or '').strip(),
            ', '.join(filter(None, [
                (getattr(loc, 'city', None) or '').strip(),
                (getattr(loc, 'state', None) or '').strip(),
                (getattr(loc, 'zip_code', None) or '').strip(),
            ])).strip(),
            ('Phone: ' + (getattr(loc, 'phone', None) or '').strip()) if getattr(loc, 'phone', None) else '',
        ]
    else:
        lines = [
            (getattr(so, 'customer_name', None) or '').strip(),
            (getattr(so, 'customer_address', None) or '').strip(),
            ', '.join(filter(None, [
                (getattr(so, 'customer_city', None) or '').strip(),
                (getattr(so, 'customer_state', None) or '').strip(),
                (getattr(so, 'customer_zip', None) or '').strip(),
            ])).strip(),
            ('Phone: ' + (getattr(so, 'customer_phone', None) or '').strip()) if getattr(so, 'customer_phone', None) else '',
        ]
    return [l for l in lines if l]


def generate_invoice_pdf(invoice):
    """Generate invoice PDF with template-style layout and styling to match Invoice template.pdf (Arial 9pt/20pt, light gray headers, thin borders)."""
    _register_invoice_fonts()
    # Use Arial if both registered (template uses Arial 9pt/20pt), else Helvetica
    try:
        pdfmetrics.getFont('Arial')
        pdfmetrics.getFont('Arial-Bold')
        body_font, bold_font = 'Arial', 'Arial-Bold'
    except Exception:
        body_font, bold_font = 'Helvetica', 'Helvetica-Bold'

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.5*inch,
        bottomMargin=0.65*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
    )
    story = []
    styles = getSampleStyleSheet()
    black = colors.black
    gray = colors.HexColor('#5a5a5a')
    header_bg = colors.HexColor('#e8e8e8')
    border_color = colors.HexColor('#d0d0d0')
    font_9 = 9
    font_20 = 20

    small = ParagraphStyle('Small', parent=styles['Normal'], fontSize=font_9, textColor=black, fontName=body_font)
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=font_9, textColor=black, fontName=bold_font)

    # ----- Header: logo + company left; INVOICE 20pt bold right -----
    logo_path = get_batch_ticket_logo_path() or get_logo_path()
    logo_w, logo_h = 2.5*inch, 2.5*inch
    logo_col_w = 2.2*inch
    logo_cell = None
    if logo_path and os.path.exists(logo_path):
        try:
            logo_cell = _FixedSizeImage(logo_path, logo_w, logo_h)
        except Exception:
            try:
                with open(logo_path, 'rb') as f:
                    logo_cell = _FixedSizeImage(BytesIO(f.read()), logo_w, logo_h)
            except Exception:
                pass
    if not logo_cell:
        logo_cell = Paragraph('Wildwood Ingredients, LLC', ParagraphStyle('Co', parent=styles['Normal'], fontSize=font_9, fontName=bold_font, textColor=black))
    company_addr = Paragraph(
        '6431 Michels Drive, Washington, MO 63090<br/>Phone: 314-835-8207',
        ParagraphStyle('Addr', parent=styles['Normal'], fontSize=font_9, fontName=bold_font, textColor=black),
    )
    inv_num = (getattr(invoice, 'invoice_number', None) or '').strip()
    inv_date = invoice.invoice_date.strftime('%m/%d/%Y') if getattr(invoice, 'invoice_date', None) else ''
    title_style = ParagraphStyle('InvTitle', parent=styles['Normal'], fontSize=font_20, fontName=bold_font, textColor=black, alignment=TA_RIGHT, spaceAfter=8)
    meta_style = ParagraphStyle('InvMeta', parent=styles['Normal'], fontSize=font_9, fontName=body_font, textColor=black, alignment=TA_RIGHT)
    # Use nested Table instead of KeepTogether to avoid ReportLab "tallest cell 16777221" layout bug
    right_cell = Table(
        [[Paragraph('INVOICE', title_style)], [Paragraph(f'INVOICE # {inv_num}<br/>DATE: {inv_date}', meta_style)]],
        colWidths=[4.3*inch], rowHeights=[0.35*inch, 0.3*inch]
    )
    right_cell.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (0, 0), (-1, -1), 'RIGHT')]))
    header_tbl = Table([[logo_cell, right_cell], [company_addr, '']], colWidths=[logo_col_w, 4.3*inch])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 0.22*inch))

    # ----- BILL TO | SHIP TO (9pt bold labels, 9pt body - template feel) -----
    bill_lines, payment_terms = _invoice_bill_to(invoice)
    ship_lines = _invoice_ship_to(invoice)
    bill_text = '<br/>'.join(bill_lines) if bill_lines else '—'
    ship_text = '<br/>'.join(ship_lines) if ship_lines else '—'
    so = getattr(invoice, 'sales_order', None)
    cust_ref = (getattr(so, 'customer_reference_number', None) or '').strip() if so else ''
    po_num = cust_ref
    so_num = (getattr(so, 'so_number', None) or '').strip() if so else ''
    carrier = (getattr(so, 'carrier', None) or '').strip() if so else ''
    track = (getattr(so, 'tracking_number', None) or '').strip() if so else ''
    shipped_via = ' '.join(filter(None, [carrier, track])).strip() or '—'
    so_notes = (getattr(so, 'notes', None) or '').strip() if so else ''
    inv_notes = (getattr(invoice, 'notes', None) or '').strip()
    comments_text = ' '.join(filter(None, [so_notes, inv_notes])).strip()

    p_style = ParagraphStyle('Block', parent=styles['Normal'], fontSize=font_9, textColor=black, fontName=body_font)
    bill_para = Paragraph(f'<b>BILL TO:</b><br/>{bill_text}', p_style)
    ship_para = Paragraph(f'<b>SHIP TO:</b><br/>{ship_text}', p_style)
    two_col = Table([[bill_para, ship_para]], colWidths=[3.2*inch, 3.2*inch])
    two_col.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(two_col)
    story.append(Spacer(1, 0.18*inch))

    # ----- COMMENTS OR SPECIAL INSTRUCTIONS: indent to line up with tables (right of logo column) -----
    comments_indent = 2.2*inch
    comments_label_style = ParagraphStyle('CommentsLabel', parent=label_style, leftIndent=comments_indent)
    comments_body_style = ParagraphStyle('CommentsBody', parent=small, leftIndent=comments_indent)
    if comments_text:
        story.append(Paragraph('<b>COMMENTS OR SPECIAL INSTRUCTIONS:</b>', comments_label_style))
        story.append(Paragraph(comments_text.replace('&', '&amp;'), comments_body_style))
        story.append(Spacer(1, 0.14*inch))

    # ----- Reference row: light gray header row, thin borders (template style) -----
    ref_headers = ['CUST REF #', 'P.O. NUMBER', 'S.O. NUMBER', 'SHIPPED VIA', 'PAYMENT TERMS']
    ref_row = [cust_ref or '—', po_num or '—', so_num or '—', shipped_via, payment_terms or '—']
    ref_tbl = Table([ref_headers, ref_row], colWidths=[1.15*inch, 1.15*inch, 1.15*inch, 1.4*inch, 1.15*inch])
    ref_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('FONTNAME', (0, 0), (-1, 0), bold_font),
        ('FONTNAME', (0, 1), (-1, 1), body_font),
        ('FONTSIZE', (0, 0), (-1, -1), font_9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(ref_tbl)
    story.append(Spacer(1, 0.2*inch))

    # ----- Line items: same light gray header, thin borders, 9pt throughout -----
    try:
        items = list(invoice.items.all())
    except Exception:
        items = []
    row_headers = ['QUANTITY', 'DESCRIPTION', 'LOT #', 'UNIT PRICE', 'TOTAL']
    rows = [row_headers]
    for it in items:
        desc = (getattr(it, 'description', None) or '').strip()
        if not desc and getattr(it, 'item', None):
            desc = (getattr(it.item, 'name', None) or getattr(it.item, 'sku', None) or '').strip()
        lot = (getattr(it, 'lot_number', None) or '').strip()
        qty = getattr(it, 'quantity', None)
        up = getattr(it, 'unit_price', None)
        total = getattr(it, 'total', None)
        if total is None and qty is not None and up is not None:
            total = qty * up
        rows.append([
            f"{qty:.2f}" if qty is not None else '—',
            desc or '—',
            lot or '—',
            f"${up:,.2f}" if up is not None else '—',
            f"${total:,.2f}" if total is not None else '—',
        ])
    if len(rows) == 1:
        rows.append(['—', '—', '—', '—', '—'])
    items_tbl = Table(rows, colWidths=[0.75*inch, 2.5*inch, 1.0*inch, 0.9*inch, 0.9*inch])
    items_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('FONTNAME', (0, 0), (-1, 0), bold_font),
        ('FONTNAME', (0, 1), (-1, -1), body_font),
        ('FONTSIZE', (0, 0), (-1, -1), font_9),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 0.22*inch))

    # ----- Totals: 9pt labels, bold 9pt for TOTAL DUE, thin line above total -----
    subtotal = getattr(invoice, 'subtotal', None)
    if subtotal is None and items:
        subtotal = sum((getattr(it, 'total', None) or 0) for it in items)
    subtotal = subtotal or 0.0
    tax = getattr(invoice, 'tax', None) or 0.0
    freight = getattr(invoice, 'freight', None) or 0.0
    grand = getattr(invoice, 'grand_total', None)
    if grand is None:
        grand = subtotal + tax + freight

    totals_data = [
        ['SUBTOTAL', f"${subtotal:,.2f}"],
        ['SALES TAX', f"${tax:,.2f}"],
        ['SHIPPING', f"${freight:,.2f}"],
        ['TOTAL DUE', f"${grand:,.2f}"],
    ]
    tot_tbl = Table(totals_data, colWidths=[1.2*inch, 1.5*inch])
    tot_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), body_font),
        ('FONTNAME', (1, 0), (1, -1), body_font),
        ('FONTNAME', (0, -1), (-1, -1), bold_font),
        ('FONTSIZE', (0, 0), (-1, -1), font_9),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1, 0.28*inch))

    # ----- Footer (9pt regular, gray - template text) -----
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=font_9, textColor=gray, alignment=TA_CENTER, fontName=body_font)
    story.append(Paragraph('Make all checks payable to Wildwood Ingredients, LLC.', footer_style))
    story.append(Paragraph('Thank you for your business! For invoice related questions, contact Greg Morris: greg.morris@wildwoodingredients.com.', footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_purchase_order_pdf(purchase_order):
    """Generate purchase order PDF matching PO template1 layout: address left, PURCHASE ORDER + Status right, meta grid, Vendor/Bill To/Ship To, Line Items (#/Description/Qty/Unit/Unit Price/Tax %/Line Total), Summary."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
    )
    story = []
    styles = getSampleStyleSheet()
    black = colors.black
    gray = colors.HexColor('#5a5a5a')
    border_color = colors.HexColor('#888888')  # visible table borders
    border_light = colors.HexColor('#b0b0b0')
    header_bg = colors.HexColor('#e0e0e0')     # visible header fill
    zebra_bg = colors.HexColor('#f5f5f5')      # alternating row fill
    font_8 = 8
    font_9 = 9
    font_10 = 10
    font_18 = 18
    space_sm = 0.12*inch
    space_md = 0.2*inch

    # ----- Header: left = company address (template style); right = PURCHASE ORDER + Status -----
    # Use plain table for address to avoid Paragraph reporting bad height in some ReportLab versions
    company_addr_tbl = Table([
        ['6431 Michels Drive'],
        ['Washington, MO 63090'],
    ], colWidths=[2.2*inch], rowHeights=[12, 12])
    company_addr_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), font_9),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    po_title_style = ParagraphStyle('POTitle', parent=styles['Normal'], fontSize=font_18, fontName='Helvetica-Bold', textColor=black, alignment=TA_RIGHT, spaceAfter=4)
    status_label = (purchase_order.status or 'draft').capitalize()
    status_style = ParagraphStyle('POStatus', parent=styles['Normal'], fontSize=font_9, fontName='Helvetica-Bold', textColor=black, alignment=TA_RIGHT)
    right_cell = Table(
        [[Paragraph('PURCHASE ORDER', po_title_style)], [Paragraph(f'Status: {status_label}', status_style)]],
        colWidths=[4.3*inch],
        rowHeights=[22, 14],
    )
    right_cell.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    header_tbl = Table([[company_addr_tbl, right_cell]], colWidths=[2.2*inch, 4.3*inch], rowHeights=[0.65*inch])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, space_sm))

    # ----- Meta block: PO Number, PO Date, Requested By | Delivery Date, Payment Terms, Ship Via -----
    order_date_str = purchase_order.order_date.strftime('%b %d, %Y') if purchase_order.order_date else '—'
    delivery_str = (purchase_order.expected_delivery_date or purchase_order.required_date)
    delivery_str = delivery_str.strftime('%b %d, %Y') if delivery_str else '—'
    ship_via = (getattr(purchase_order, 'shipping_method', None) or getattr(purchase_order, 'carrier', None) or '').strip() or '—'
    payment_terms = '—'
    try:
        from .models import Vendor
        v = Vendor.objects.filter(name=purchase_order.vendor_customer_name).first()
        if v and getattr(v, 'payment_terms', None):
            payment_terms = (v.payment_terms or '').strip()
    except Exception:
        pass
    requested_by = getattr(purchase_order, 'requested_by', None) or '—'
    meta_labels = ['PO Number', 'PO Date', 'Requested By', 'Delivery Date', 'Payment Terms', 'Ship Via']
    meta_values = [
        purchase_order.po_number or '—',
        order_date_str,
        requested_by,
        delivery_str,
        payment_terms,
        ship_via,
    ]
    meta_tbl = Table([
        meta_labels[:3], meta_values[:3],
        meta_labels[3:], meta_values[3:],
    ], colWidths=[1.05*inch, 1.6*inch, 1.05*inch])
    meta_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), font_8),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.75, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_light),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, space_md))

    # ----- VENDOR & SHIPPING DETAILS: three columns (Vendor/Supplier | Bill To | Ship To) -----
    vendor_name = purchase_order.vendor_customer_name or '—'
    vendor_addr1 = (purchase_order.vendor_address or '').strip() or '—'
    vendor_csz = ', '.join(filter(None, [purchase_order.vendor_city, purchase_order.vendor_state, purchase_order.vendor_zip]))
    vendor_addr2 = vendor_csz or '—'
    bill_to_name = 'Wildwood Ingredients, LLC'
    bill_to_addr1 = '6431 Michels Drive'
    bill_to_addr2 = 'Washington, MO 63090'
    ship_to_name = purchase_order.ship_to_name or '—'
    ship_to_addr1 = (purchase_order.ship_to_address or '').strip() or '—'
    ship_to_csz = ', '.join(filter(None, [purchase_order.ship_to_city, purchase_order.ship_to_state, purchase_order.ship_to_zip]))
    ship_to_addr2 = ship_to_csz or '—'
    section_style = ParagraphStyle('POSection', parent=styles['Normal'], fontSize=font_10, fontName='Helvetica-Bold', textColor=black, spaceAfter=4)
    label_style = ParagraphStyle('POLabel', parent=styles['Normal'], fontSize=font_9, fontName='Helvetica-Bold', textColor=black)
    value_style = ParagraphStyle('POValue', parent=styles['Normal'], fontSize=font_10, textColor=black)
    story.append(Paragraph('VENDOR & SHIPPING DETAILS', section_style))
    details_data = [
        [Paragraph('Vendor / Supplier', label_style), Paragraph('Bill To', label_style), Paragraph('Ship To', label_style)],
        [Paragraph(vendor_name, value_style), Paragraph(bill_to_name, value_style), Paragraph(ship_to_name, value_style)],
        [Paragraph('—', value_style), Paragraph('—', value_style), Paragraph('—', value_style)],
        [Paragraph(vendor_addr1, value_style), Paragraph(bill_to_addr1, value_style), Paragraph(ship_to_addr1, value_style)],
        [Paragraph(vendor_addr2, value_style), Paragraph(bill_to_addr2, value_style), Paragraph(ship_to_addr2, value_style)],
    ]
    details_tbl = Table(details_data, colWidths=[2.1*inch, 2.1*inch, 2.1*inch])
    details_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.75, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_light),
    ]))
    story.append(details_tbl)
    story.append(Spacer(1, space_md))

    # ----- LINE ITEMS: # | Description | Qty | Unit | Unit Price | Tax % | Line Total -----
    story.append(Paragraph('LINE ITEMS', section_style))
    use_vendor_display = getattr(purchase_order, 'po_type', None) == 'vendor'
    vendor_item_number_by_item_id = {}
    if use_vendor_display and purchase_order.vendor_customer_name:
        try:
            from .models import VendorPricing
            item_ids = [pi.item_id for pi in purchase_order.items.all() if pi.item_id]
            if item_ids:
                for vp in VendorPricing.objects.filter(
                    vendor_name=purchase_order.vendor_customer_name,
                    item_id__in=item_ids,
                    is_active=True,
                ).order_by('item_id', '-effective_date').values('item_id', 'vendor_item_number'):
                    iid = vp['item_id']
                    if vp.get('vendor_item_number') and iid not in vendor_item_number_by_item_id:
                        vendor_item_number_by_item_id[iid] = vp['vendor_item_number']
        except Exception:
            pass
    row_headers = ['#', 'Description', 'Qty', 'Unit', 'Unit Price', 'Tax %', 'Line Total']
    items_rows = [row_headers]
    for idx, po_item in enumerate(purchase_order.items.select_related('item').all(), 1):
        item = po_item.item
        if use_vendor_display and item:
            desc = item.vendor_item_name or item.name or (po_item.notes or '—') or '—'
        else:
            desc = (item.name if item else (po_item.notes or '—')) or '—'
        uom = (item.unit_of_measure if item else 'lbs') or 'lbs'
        qty = po_item.quantity_ordered
        up = po_item.unit_price or 0
        line_total = qty * up
        items_rows.append([
            str(idx),
            desc[:60] + ('…' if len(desc) > 60 else ''),
            f"{qty:,.2f}",
            uom,
            f"${up:,.2f}",
            '—',
            f"${line_total:,.2f}",
        ])
    col_w = [0.35*inch, 2.0*inch, 0.55*inch, 0.45*inch, 0.7*inch, 0.5*inch, 0.75*inch]
    items_tbl = Table(items_rows, colWidths=col_w)
    items_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), font_9),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('BOX', (0, 0), (-1, -1), 0.75, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_light),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, zebra_bg]),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, space_md))

    # ----- SUMMARY: Notes/Instructions, then Subtotal, Shipping, Tax, Discount, Total -----
    story.append(Paragraph('SUMMARY', section_style))
    notes_text = (getattr(purchase_order, 'notes', None) or '').strip() or '—'
    notes_para = Paragraph(notes_text.replace('&', '&amp;'), value_style)
    story.append(Paragraph('Notes / Instructions', label_style))
    story.append(notes_para)
    story.append(Spacer(1, space_sm))
    subtotal = sum((pi.quantity_ordered * (pi.unit_price or 0)) for pi in purchase_order.items.all())
    subtotal = round(subtotal, 2)
    discount = float(getattr(purchase_order, 'discount', 0) or 0)
    shipping_cost = float(getattr(purchase_order, 'shipping_cost', 0) or 0)
    total = round(subtotal - discount + shipping_cost, 2)
    summary_rows = [
        ['Subtotal', f"${subtotal:,.2f}"],
        ['Shipping', f"${shipping_cost:,.2f}"],
        ['Tax', '$0.00'],
        ['Discount', f"-${discount:,.2f}"],
        ['Total', f"${total:,.2f}"],
    ]
    summary_tbl = Table(summary_rows, colWidths=[1.2*inch, 1.4*inch])
    summary_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -2), font_10),
        ('FONTSIZE', (0, -1), (-1, -1), font_10),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.75, border_color),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, border_light),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, black),
        ('BACKGROUND', (0, -1), (-1, -1), zebra_bg),
    ]))
    story.append(summary_tbl)

    footer_style = ParagraphStyle('POFooter', parent=styles['Normal'], fontSize=8, textColor=gray, alignment=TA_CENTER, spaceBefore=12)
    story.append(Paragraph(f"Purchase Order {purchase_order.po_number} — Generated {datetime.now().strftime('%m/%d/%Y %H:%M')}", footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_sales_order_pdf(sales_order):
    """Generate PDF for sales order"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Add logo in upper left corner
    add_logo_header(story)
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Header
    story.append(Paragraph("SALES ORDER CONFIRMATION", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # SO details
    so_data = [
        ['SO Number:', sales_order.so_number],
        ['Order Date:', sales_order.order_date.strftime('%Y-%m-%d') if sales_order.order_date else 'N/A'],
        ['Expected Ship Date:', sales_order.expected_ship_date.strftime('%Y-%m-%d') if sales_order.expected_ship_date else 'N/A'],
        ['Customer:', sales_order.customer_name],
        ['Status:', sales_order.status.upper()],
    ]
    
    if sales_order.customer_reference_number:
        so_data.append(['Customer PO:', sales_order.customer_reference_number])
    
    so_table = Table(so_data, colWidths=[2*inch, 4*inch])
    so_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(so_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Line items
    items_data = [['Item', 'Description', 'Quantity Ordered', 'Unit Price', 'Total']]
    for item in sales_order.items.all():
        items_data.append([
            item.item.sku if item.item else 'N/A',
            item.item.name if item.item else 'N/A',
            f"{item.quantity_ordered:.2f}",
            f"${item.unit_price:.2f}" if item.unit_price else '$0.00',
            f"${(item.quantity_ordered * (item.unit_price or 0)):.2f}"
        ])
    
    items_table = Table(items_data, colWidths=[1*inch, 2*inch, 1.5*inch, 1*inch, 1*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(items_table)
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
