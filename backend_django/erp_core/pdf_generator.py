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


def get_logo_path():
    """Get the path to the Wildwood Ingredients logo.
    Looks in: batch_ticket_template/, Sensitive/, then frontend/public/logo.png.
    """
    base = Path(__file__).resolve().parent.parent.parent  # WWI ERP project root
    backend = Path(__file__).resolve().parent.parent  # backend_django
    names = ['Wildwood Ingredients Logo - Transparent Background.png', 'logo.png', 'Logo.png']
    # 1) batch_ticket_template (same folder as batch ticket template; often has logo next to it)
    template_dir = backend / 'batch_ticket_template'
    if template_dir.exists():
        for name in names:
            p = template_dir / name
            if p.exists():
                return str(p)
    # 2) Sensitive (production)
    sensitive = base / 'Sensitive'
    if sensitive.exists():
        for name in names:
            p = sensitive / name
            if p.exists():
                return str(p)
    # 3) frontend/public (development)
    frontend_path = base / 'frontend' / 'public' / 'logo.png'
    if frontend_path.exists():
        return str(frontend_path)
    return None


def add_logo_header(story, logo_path=None):
    """Add logo in upper left corner"""
    if logo_path is None:
        logo_path = get_logo_path()
    
    if logo_path and os.path.exists(logo_path):
        try:
            # Create a table with logo on left and empty space on right
            logo_img = Image(logo_path, width=2*inch, height=0.75*inch, preserveAspectRatio=True)
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
    """Generate PDF for purchase order"""
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
    story.append(Paragraph("PURCHASE ORDER", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Build vendor address from structured fields
    vendor_address_lines = []
    if purchase_order.vendor_address:
        vendor_address_lines.append(purchase_order.vendor_address)
    if purchase_order.vendor_city or purchase_order.vendor_state or purchase_order.vendor_zip:
        city_state_zip = []
        if purchase_order.vendor_city:
            city_state_zip.append(purchase_order.vendor_city)
        if purchase_order.vendor_state:
            city_state_zip.append(purchase_order.vendor_state)
        if purchase_order.vendor_zip:
            city_state_zip.append(purchase_order.vendor_zip)
        vendor_address_lines.append(', '.join(city_state_zip))
    if purchase_order.vendor_country:
        vendor_address_lines.append(purchase_order.vendor_country)
    vendor_address = '\n'.join(vendor_address_lines) if vendor_address_lines else 'N/A'
    
    # Build shipping address (where vendor should ship to)
    ship_to_lines = []
    if purchase_order.ship_to_name:
        ship_to_lines.append(purchase_order.ship_to_name)
    if purchase_order.ship_to_address:
        ship_to_lines.append(purchase_order.ship_to_address)
    if purchase_order.ship_to_city or purchase_order.ship_to_state or purchase_order.ship_to_zip:
        city_state_zip = []
        if purchase_order.ship_to_city:
            city_state_zip.append(purchase_order.ship_to_city)
        if purchase_order.ship_to_state:
            city_state_zip.append(purchase_order.ship_to_state)
        if purchase_order.ship_to_zip:
            city_state_zip.append(purchase_order.ship_to_zip)
        ship_to_lines.append(', '.join(city_state_zip))
    if purchase_order.ship_to_country:
        ship_to_lines.append(purchase_order.ship_to_country)
    ship_to_address = '\n'.join(ship_to_lines) if ship_to_lines else 'N/A'
    
    # PO details
    po_data = [
        ['PO Number:', purchase_order.po_number],
        ['Order Date:', purchase_order.order_date.strftime('%Y-%m-%d') if purchase_order.order_date else 'N/A'],
        ['Expected Delivery:', purchase_order.expected_delivery_date.strftime('%Y-%m-%d') if purchase_order.expected_delivery_date else 'N/A'],
        ['Vendor:', purchase_order.vendor_customer_name],
        ['Vendor Address:', vendor_address],
        ['Ship To:', ship_to_address],
        ['Status:', purchase_order.status.upper()],
    ]
    
    po_table = Table(po_data, colWidths=[2*inch, 4*inch])
    po_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(po_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Line items
    items_data = [['Item', 'Description', 'Quantity', 'Unit Price', 'Total']]
    for item in purchase_order.items.all():
        item_name = item.item.name if item.item else 'N/A'
        items_data.append([
            item.item.sku if item.item else 'N/A',
            item_name,
            f"{item.quantity_ordered:.2f}",
            f"${item.unit_price:.2f}" if item.unit_price else '$0.00',
            f"${(item.quantity_ordered * (item.unit_price or 0)):.2f}"
        ])
    
    items_table = Table(items_data, colWidths=[1*inch, 2*inch, 1*inch, 1*inch, 1*inch])
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
