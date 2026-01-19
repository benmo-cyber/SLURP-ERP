"""
Test script to verify email connection and authentication
"""
import os
import sys
import django
from pathlib import Path
import smtplib
from email.mime.text import MIMEText

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.conf import settings

def test_email_connection():
    """Test SMTP connection with detailed error reporting"""
    print("Testing email connection...")
    print(f"SMTP Host: {settings.EMAIL_HOST}")
    print(f"SMTP Port: {settings.EMAIL_PORT}")
    print(f"Use TLS: {settings.EMAIL_USE_TLS}")
    print(f"From Email: {settings.DEFAULT_FROM_EMAIL}")
    print(f"Email User: {settings.EMAIL_HOST_USER}")
    print(f"Password: {'*' * len(settings.EMAIL_HOST_PASSWORD)}")
    print()
    
    try:
        # Create SMTP connection
        print("Connecting to SMTP server...")
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        print("Connected successfully")
        
        # Start TLS
        if settings.EMAIL_USE_TLS:
            print("Starting TLS...")
            server.starttls()
            print("TLS started")
        
        # Login
        print("Attempting to authenticate...")
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        print("Authentication successful!")
        
        # Test sending a simple email
        print("\nSending test email...")
        msg = MIMEText("This is a test email from SLURP ERP system.")
        msg['Subject'] = 'Test Email from SLURP'
        msg['From'] = settings.DEFAULT_FROM_EMAIL
        msg['To'] = 'ben.morris640@gmail.com'
        
        server.send_message(msg)
        print("Test email sent successfully!")
        
        server.quit()
        print("\nSUCCESS: Email connection and authentication working correctly!")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\nERROR: Authentication failed")
        print(f"Error code: {e.smtp_code}")
        print(f"Error message: {e.smtp_error}")
        print("\nPossible issues:")
        print("1. Password might be incorrect")
        print("2. Account might require an App Password (if MFA is enabled)")
        print("3. SMTP AUTH might be disabled at the tenant level")
        print("4. Account might be locked or suspended")
        return False
        
    except smtplib.SMTPException as e:
        print(f"\nERROR: SMTP error occurred")
        print(f"Error: {str(e)}")
        return False
        
    except Exception as e:
        print(f"\nERROR: Unexpected error")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    test_email_connection()
