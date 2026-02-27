"""
PDF generation for invoices, purchase orders, and sales orders
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from django.utils import timezone
from datetime import datetime
from pathlib import Path
import os
import shutil
import logging

logger = logging.getLogger(__name__)


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


def generate_invoice_pdf(invoice):
    """Generate PDF for invoice"""
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
    story.append(Paragraph("INVOICE", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Invoice details
    invoice_data = [
        ['Invoice Number:', invoice.invoice_number],
        ['Invoice Date:', invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else 'N/A'],
        ['Due Date:', invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else 'N/A'],
        ['Status:', invoice.status.upper()],
    ]
    
    if invoice.sales_order:
        invoice_data.append(['Sales Order:', invoice.sales_order.so_number])
        if invoice.sales_order.customer:
            invoice_data.append(['Customer:', invoice.sales_order.customer.name])
    
    invoice_table = Table(invoice_data, colWidths=[2*inch, 4*inch])
    invoice_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(invoice_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Line items
    items_data = [['Description', 'Quantity', 'Unit Price', 'Total']]
    for item in invoice.items.all():
        description = item.description or 'N/A'
        if not item.description and hasattr(item, 'sales_order_item') and item.sales_order_item:
            if hasattr(item.sales_order_item, 'item') and item.sales_order_item.item:
                description = item.sales_order_item.item.name
        
        items_data.append([
            description,
            f"{item.quantity:.2f}",
            f"${item.unit_price:.2f}",
            f"${item.total:.2f}"
        ])
    
    items_table = Table(items_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Totals - handle missing fields gracefully
    totals_data = [
        ['Subtotal:', f"${getattr(invoice, 'subtotal', 0.0):.2f}"],
    ]
    
    freight = getattr(invoice, 'freight', None)
    if freight is not None:
        totals_data.append(['Freight:', f"${freight:.2f}"])
    
    tax = getattr(invoice, 'tax', None)
    if tax is not None:
        totals_data.append(['Tax:', f"${tax:.2f}"])
    
    discount = getattr(invoice, 'discount', None)
    if discount is not None:
        totals_data.append(['Discount:', f"-${discount:.2f}"])
    
    grand_total = getattr(invoice, 'grand_total', None)
    if grand_total is None:
        # Calculate from subtotal and other fields
        grand_total = getattr(invoice, 'subtotal', 0.0)
        if freight is not None:
            grand_total += freight
        if tax is not None:
            grand_total += tax
        if discount is not None:
            grand_total -= discount
    
    totals_data.append(['TOTAL:', f"${grand_total:.2f}"])
    
    totals_table = Table(totals_data, colWidths=[4*inch, 2*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('FONTSIZE', (0, 0), (0, -2), 10),
        ('TOPPADDING', (0, -1), (-1, -1), 12),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 12),
        ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
    ]))
    story.append(totals_table)
    
    # Notes
    if invoice.notes:
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f"<b>Notes:</b> {invoice.notes}", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_purchase_order_pdf(purchase_order):
    """Generate PDF for purchase order — stylish layout (logo, Vendor/Ship to, shipping block, line items, totals)."""
    # Stylish palette: SLURP blue + light tints
    blue_dark = colors.HexColor('#2c3e50')
    blue_medium = colors.HexColor('#3d5a73')
    blue_light_bg = colors.HexColor('#f0f4f8')
    blue_very_light = colors.HexColor('#f5f8fc')  # very subtle blue for alternating item rows
    blue_border = colors.HexColor('#a8b8c8')
    gray = colors.HexColor('#5a6575')
    gray_light = colors.HexColor('#eef1f5')

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
    space_sm = 0.14*inch
    space_md = 0.24*inch

    # ----- Logo: top-left; right: "PURCHASE ORDER #" with accent -----
    logo_path = _get_po_logo_path()
    logo_cell = ''
    if logo_path:
        try:
            # Prefer path (ReportLab handles PNG from path); fallback to bytes for portability
            logo_img = Image(logo_path, width=1.5*inch, height=1.5*inch)
            logo_cell = logo_img
        except Exception:
            try:
                with open(logo_path, 'rb') as f:
                    logo_data = f.read()
                stream = BytesIO(logo_data)
                stream.seek(0)
                logo_img = Image(stream, width=1.5*inch, height=1.5*inch)
                logo_cell = logo_img
            except Exception as e:
                logger.warning("PO PDF: could not load logo from %s: %s", logo_path, e)
    if not logo_cell:
        logger.warning("PO PDF: no logo found (path=%s). Using placeholder.", logo_path)
        logo_cell = Paragraph('Logo', ParagraphStyle('LogoPlaceholder', parent=styles['Normal'], fontSize=10, textColor=blue_dark))

    order_date_str = purchase_order.order_date.strftime('%m/%d/%Y') if purchase_order.order_date else 'MM/DD/YYYY'
    order_ref = (purchase_order.order_number or purchase_order.po_number or '—').strip()
    po_title_style = ParagraphStyle(
        'POTitle', parent=styles['Heading1'], fontSize=18, textColor=blue_dark,
        spaceAfter=6, spaceBefore=0, alignment=TA_RIGHT, fontName='Helvetica-Bold',
    )
    title_para = Paragraph(f"PURCHASE ORDER #{purchase_order.po_number or '—'}", po_title_style)
    po_meta = [
        ['Date:', order_date_str],
        ['order #:', order_ref],
    ]
    po_meta_tbl = Table(po_meta, colWidths=[0.9*inch, 2.0*inch])
    po_meta_tbl.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), gray),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    right_cell = Table([[title_para], [po_meta_tbl]], colWidths=[3.5*inch])
    right_cell.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    header_tbl = Table([[logo_cell, right_cell]], colWidths=[2.5*inch, 3.5*inch])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 2.5, blue_medium),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, space_md))

    # ----- Vendor | Ship to (template: two columns, labels then addresses) -----
    vendor_lines = [purchase_order.vendor_customer_name or 'Vendor']
    if purchase_order.vendor_address:
        vendor_lines.append(purchase_order.vendor_address)
    csz = [x for x in [purchase_order.vendor_city, purchase_order.vendor_state, purchase_order.vendor_zip] if x]
    if csz:
        vendor_lines.append(', '.join(csz))
    if purchase_order.vendor_country:
        vendor_lines.append(purchase_order.vendor_country)
    vendor_text = '\n'.join(vendor_lines) if vendor_lines else '—'

    ship_lines = [purchase_order.ship_to_name or 'Ship to']
    if purchase_order.ship_to_address:
        ship_lines.append(purchase_order.ship_to_address)
    csz = [x for x in [purchase_order.ship_to_city, purchase_order.ship_to_state, purchase_order.ship_to_zip] if x]
    if csz:
        ship_lines.append(', '.join(csz))
    if purchase_order.ship_to_country:
        ship_lines.append(purchase_order.ship_to_country)
    ship_text = '\n'.join(ship_lines) if ship_lines else '—'

    normal_9 = ParagraphStyle('NormalPO', parent=styles['Normal'], fontSize=9, spaceAfter=1, spaceBefore=0)
    label_white = ParagraphStyle('LabelPO', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', textColor=colors.white, spaceAfter=4, spaceBefore=0)
    addr_tbl = Table([
        [Paragraph('Vendor', label_white), Paragraph('Ship to', label_white)],
        [Paragraph(vendor_text.replace('\n', '<br/>'), normal_9), Paragraph(ship_text.replace('\n', '<br/>'), normal_9)],
    ], colWidths=[3.25*inch, 3.25*inch])
    addr_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (1, 0), blue_dark),
        ('BACKGROUND', (0, 1), (0, 1), blue_light_bg),
        ('BACKGROUND', (1, 1), (1, 1), blue_light_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, blue_border),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(addr_tbl)
    story.append(Spacer(1, space_md))

    # ----- Shipping terms | Shipping method | Delivery date (same width as Vendor/Ship to: 6.5") -----
    shipping_terms = getattr(purchase_order, 'shipping_terms', None) or '—'
    shipping_method = getattr(purchase_order, 'shipping_method', None) or getattr(purchase_order, 'carrier', None) or '—'
    delivery_str = purchase_order.expected_delivery_date.strftime('%m/%d/%y') if purchase_order.expected_delivery_date else '—'
    ship_col_w = [1.6*inch, 1.6*inch, 1.6*inch, 1.7*inch]  # total 6.5"
    ship_block = Table([
        ['Shipping terms', 'Shipping method', '', 'Delivery date'],
        [shipping_terms, shipping_method, '', delivery_str],
    ], colWidths=ship_col_w)
    ship_block.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), gray),
        ('BACKGROUND', (0, 0), (-1, 0), gray_light),
        ('BOX', (0, 0), (-1, -1), 0.5, blue_border),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(ship_block)
    story.append(Spacer(1, space_md))

    # ----- Line items: Item # | Description | Unit cost (UoM) | Qty (UoM) | Amount -----
    # For vendor POs use vendor item # and vendor description; otherwise WWI SKU and name
    use_vendor_display = getattr(purchase_order, 'po_type', None) == 'vendor'
    vendor_item_number_by_item_id = {}
    if use_vendor_display and purchase_order.vendor_customer_name:
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
    items_headers = ['Item #', 'Description', 'Unit cost', 'Qty', 'Amount']
    items_rows = [items_headers]
    for po_item in purchase_order.items.select_related('item').all():
        item = po_item.item
        if use_vendor_display and item:
            item_num = vendor_item_number_by_item_id.get(item.id) or item.vendor_item_name or item.sku or '—'
            desc = item.vendor_item_name or item.name or (po_item.notes or '—') or '—'
        else:
            item_num = item.sku if item else '—'
            desc = (item.name if item else (po_item.notes or '—')) or '—'
        if len(desc) > 50:
            desc = desc[:50] + '…'
        uom = (item.unit_of_measure if item else 'lbs') or 'lbs'
        qty = po_item.quantity_ordered
        up = po_item.unit_price or 0
        line_total = qty * up
        items_rows.append([
            item_num,
            desc,
            f"${up:,.2f} /{uom}",
            f"{qty:,.2f} {uom}",
            f"${line_total:,.2f}",
        ])
    # Add 5 blank rows for manual entry
    for _ in range(5):
        items_rows.append(['', '', '', '', ''])
    col_w = [1.2*inch, 2.65*inch, 0.85*inch, 0.85*inch, 0.95*inch]  # total 6.5" to match tables above
    items_table = Table(items_rows, colWidths=col_w)
    item_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), blue_dark),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOX', (0, 0), (-1, -1), 0.5, blue_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, blue_border),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    # Alternate row fill: white and very subtle blue
    for i in range(1, len(items_rows)):
        if i % 2 == 0:
            item_styles.append(('BACKGROUND', (0, i), (-1, i), blue_very_light))
        else:
            item_styles.append(('BACKGROUND', (0, i), (-1, i), colors.white))
    items_table.setStyle(TableStyle(item_styles))
    story.append(items_table)
    story.append(Spacer(1, space_md))

    # ----- Totals block (template: SUBTOTAL, CoA/SDS line + DISCOUNT, SHIPPING, TOTAL) -----
    # Always compute from line items and PO fields so PDF totals are correct
    subtotal = sum((pi.quantity_ordered * (pi.unit_price or 0)) for pi in purchase_order.items.all())
    discount = float(getattr(purchase_order, 'discount', 0) or 0)
    shipping_cost = float(getattr(purchase_order, 'shipping_cost', 0) or 0)
    total = round(subtotal - discount + shipping_cost, 2)
    subtotal = round(subtotal, 2)

    coa_email = getattr(purchase_order, 'coa_sds_email', None) or ''
    default_coa_email = 'customerservice@wildwoodingredients.com'
    coa_line = f"Please email CoA, SDS and shipping documents to {coa_email.strip() or default_coa_email}"
    small_8 = ParagraphStyle('SmallPO', parent=styles['Normal'], fontSize=8, textColor=gray, spaceAfter=0, spaceBefore=0)

    totals_rows = [
        ['SUBTOTAL', f"${subtotal:,.2f}"],
        [Paragraph(coa_line, small_8), 'DISCOUNT'],
        ['', f"-${discount:,.2f}"],
        ['SHIPPING', f"${shipping_cost:,.2f}"],
        ['TOTAL', f"${total:,.2f}"],
    ]
    totals_table = Table(totals_rows, colWidths=[3.5*inch, 1.4*inch])
    totals_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('TEXTCOLOR', (0, -1), (-1, -1), blue_dark),
        ('BACKGROUND', (0, -1), (-1, -1), blue_light_bg),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, -1), (-1, -1), 2, blue_medium),
        ('BOX', (0, -1), (-1, -1), 0.5, blue_border),
    ]))
    # Same width as other tables (6.5") with totals table centered
    totals_width = 4.9 * inch
    side_margin = (6.5 * inch - totals_width) / 2
    totals_wrapper = Table([['', totals_table, '']], colWidths=[side_margin, totals_width, side_margin])
    totals_wrapper.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('LEFTPADDING', (2, 0), (2, 0), 0), ('RIGHTPADDING', (2, 0), (2, 0), 0),
    ]))
    story.append(totals_wrapper)

    if getattr(purchase_order, 'notes', None) and purchase_order.notes.strip():
        story.append(Spacer(1, space_sm))
        story.append(Paragraph(f"Notes: {purchase_order.notes.strip()}", small_8))

    footer_style = ParagraphStyle('FooterPO', parent=styles['Normal'], fontSize=7, textColor=blue_medium, alignment=TA_CENTER, spaceBefore=14)
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
