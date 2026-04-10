"""
Email service for sending invoices, purchase orders, and sales orders
"""
import os
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


def get_recipient_email(obj, email_field='email'):
    """Get recipient email address from object (customer/vendor)"""
    # Try to get email from customer/vendor object
    if hasattr(obj, 'customer') and obj.customer:
        if hasattr(obj.customer, email_field):
            email = getattr(obj.customer, email_field)
            if email:
                return email
    
    # Try to get email from vendor
    if hasattr(obj, 'vendor_customer_name'):
        # This is a purchase order - try to get vendor email
        from .models import Vendor
        try:
            vendor = Vendor.objects.filter(name=obj.vendor_customer_name).first()
            if vendor and hasattr(vendor, email_field):
                email = getattr(vendor, email_field)
                if email:
                    return email
        except Exception:
            pass
    
    # Try ship_to_location for sales orders
    if hasattr(obj, 'ship_to_location') and obj.ship_to_location:
        if hasattr(obj.ship_to_location, email_field):
            email = getattr(obj.ship_to_location, email_field)
            if email:
                return email
    
    return None


def _emails_from_customer_contact(contact):
    """Flatten emails JSON list from CustomerContact."""
    out = []
    for e in getattr(contact, 'emails', None) or []:
        s = str(e).strip()
        if s:
            out.append(s)
    return out


def send_invoice_email(invoice, pdf_content=None):
    """Send invoice email with PDF attachment. Recipients: A/P contacts (is_ap_contact=True) for the customer, or fallback to customer/ship-to email."""
    try:
        from .models import CustomerContact

        recipient_emails = []
        if invoice.sales_order and invoice.sales_order.customer:
            # Prefer contacts marked as A/P contact
            ap_contacts = CustomerContact.objects.filter(
                customer_id=invoice.sales_order.customer_id,
                is_ap_contact=True,
                is_active=True
            ).exclude(email__isnull=True).exclude(email='')
            recipient_emails = [c.email for c in ap_contacts]
        if not recipient_emails and invoice.sales_order and invoice.sales_order.customer:
            if invoice.sales_order.customer.email:
                recipient_emails = [invoice.sales_order.customer.email]
        if not recipient_emails and invoice.sales_order and invoice.sales_order.ship_to_location:
            if invoice.sales_order.ship_to_location.email:
                recipient_emails = [invoice.sales_order.ship_to_location.email]

        if not recipient_emails:
            logger.warning(f"No email address found for invoice {invoice.invoice_number}")
            return False

        # Create email
        subject = f"Invoice {invoice.invoice_number}"
        from_email = settings.DEFAULT_FROM_EMAIL
        reply_to = [settings.EMAIL_REPLY_TO]

        body = f"""
Dear Customer,

Please find attached invoice {invoice.invoice_number} for your records.

Invoice Date: {invoice.invoice_date}
Due Date: {invoice.due_date}
Total Amount: ${invoice.grand_total:,.2f}

If you have any questions, please reply to this email.

Thank you,
Wildwood Ingredients
"""

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=recipient_emails,
            reply_to=reply_to
        )

        if pdf_content:
            email.attach(
                f"Invoice_{invoice.invoice_number}.pdf",
                pdf_content,
                'application/pdf'
            )

        email.send()
        logger.info(f"Invoice email sent successfully to {recipient_emails} for invoice {invoice.invoice_number}")
        return True

    except Exception as e:
        logger.error(f"Failed to send invoice email: {str(e)}")
        return False


def send_purchase_order_email(purchase_order, pdf_content=None):
    """Send purchase order email with PDF attachment"""
    try:
        # Get vendor email
        from .models import Vendor
        recipient_email = None
        
        # Try to find vendor by name
        try:
            vendor = Vendor.objects.filter(name=purchase_order.vendor_customer_name).first()
            if vendor and hasattr(vendor, 'email'):
                recipient_email = vendor.email
        except Exception:
            pass
        
        if not recipient_email:
            logger.warning(f"No email address found for purchase order {purchase_order.po_number}")
            return False
        
        # Get contact name
        contact_name = vendor.contact_name if vendor and vendor.contact_name else 'Vendor'
        
        # Create email
        subject = f"Purchase Order {purchase_order.po_number}"
        from_email = settings.DEFAULT_FROM_EMAIL
        reply_to = [settings.EMAIL_REPLY_TO]
        
        # Email body
        body = f"""
Dear {contact_name},

Please find attached purchase order {purchase_order.po_number} for your processing.

Order Date: {purchase_order.order_date.strftime('%Y-%m-%d') if purchase_order.order_date else 'N/A'}
Expected Delivery: {purchase_order.expected_delivery_date.strftime('%Y-%m-%d') if purchase_order.expected_delivery_date else 'N/A'}

If you have any questions, please reply to this email.

Thank you,
Wildwood Ingredients
"""
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
            reply_to=reply_to
        )
        
        # Attach PDF if provided
        if pdf_content:
            email.attach(
                f"Purchase_Order_{purchase_order.po_number}.pdf",
                pdf_content,
                'application/pdf'
            )
        
        email.send()
        logger.info(f"Purchase order email sent successfully to {recipient_email} for PO {purchase_order.po_number}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send purchase order email: {str(e)}")
        return False


def send_sales_order_confirmation_email(sales_order, pdf_content=None):
    """Send sales order confirmation email with PDF attachment. Recipients: Purchasing contacts (is_purchasing_contact=True) for the customer, or fallback to customer/ship-to email."""
    try:
        from .models import CustomerContact

        recipient_emails = []
        if sales_order.customer_id:
            purchasing_contacts = CustomerContact.objects.filter(
                customer_id=sales_order.customer_id,
                is_purchasing_contact=True,
                is_active=True,
            )
            recipient_emails = []
            for c in purchasing_contacts:
                recipient_emails.extend(_emails_from_customer_contact(c))
            recipient_emails = list(dict.fromkeys(recipient_emails))
        if not recipient_emails and sales_order.customer and sales_order.customer.email:
            recipient_emails = [sales_order.customer.email]
        if not recipient_emails and sales_order.ship_to_location and sales_order.ship_to_location.email:
            recipient_emails = [sales_order.ship_to_location.email]

        if not recipient_emails:
            logger.warning(f"No email address found for sales order {sales_order.so_number}")
            return False

        subject = f"Sales Order Confirmation {sales_order.so_number}"
        from_email = settings.DEFAULT_FROM_EMAIL
        reply_to = [settings.EMAIL_REPLY_TO]

        body = f"""
Dear Customer,

Thank you for your order. Please find attached sales order confirmation {sales_order.so_number}.

Order Date: {sales_order.order_date.strftime('%Y-%m-%d') if sales_order.order_date else 'N/A'}
Expected Ship Date: {sales_order.expected_ship_date.strftime('%Y-%m-%d') if sales_order.expected_ship_date else 'N/A'}

If you have any questions, please reply to this email.

Thank you,
Wildwood Ingredients
"""

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=recipient_emails,
            reply_to=reply_to
        )

        if pdf_content:
            email.attach(
                f"Sales_Order_{sales_order.so_number}.pdf",
                pdf_content,
                'application/pdf'
            )

        email.send()
        logger.info(f"Sales order confirmation email sent successfully to {recipient_emails} for SO {sales_order.so_number}")
        return True

    except Exception as e:
        logger.error(f"Failed to send sales order confirmation email: {str(e)}")
        return False
