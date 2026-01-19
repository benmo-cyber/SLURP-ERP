# How to Enable SMTP AUTH at Tenant Level in GoDaddy Microsoft 365

## The Problem
The error message indicates: **"SmtpClientAuthentication is disabled for the Tenant"**

This means SMTP authentication needs to be enabled at the **organization/tenant level**, not just for individual accounts.

## Solution Options

### Option 1: Enable via Microsoft 365 Admin Center (If you have admin access)

1. **Go to Microsoft 365 Admin Center**
   - Visit: https://admin.microsoft.com
   - Sign in with your GoDaddy-managed Microsoft 365 admin credentials

2. **Navigate to Authentication Settings**
   - Go to: **Settings** → **Org settings**
   - Click on the **Security** tab
   - Look for **"SMTP AUTH"** or **"Authenticated SMTP"**

3. **Enable SMTP AUTH**
   - Find the setting for "SMTP AUTH" or "Authenticated SMTP"
   - Enable it for your organization
   - Save the changes

### Option 2: Contact GoDaddy Support

If you don't have direct access to the Microsoft 365 admin center, you may need to:

1. **Contact GoDaddy Support**
   - Call: 1-480-505-8877 (US) or your local support number
   - Or use their online chat support
   - Request: "Enable SMTP AUTH (SMTP Client Authentication) at the tenant level for Microsoft 365"

2. **Provide them with:**
   - Your domain: wildwoodingredients.com
   - The specific error message you're seeing
   - That you need SMTP AUTH enabled for automated email sending

### Option 3: Use App Password (If MFA is enabled)

If multi-factor authentication (MFA) is enabled on the account, you may need to:

1. **Create an App Password**
   - Go to: https://account.microsoft.com/security
   - Sign in with your Microsoft 365 account
   - Go to **Security** → **Advanced security options**
   - Under **App passwords**, create a new app password
   - Use this app password instead of your regular password in the Django settings

2. **Update Django Settings**
   - Replace `EMAIL_HOST_PASSWORD` in `settings.py` with the app password

## Alternative: Use Microsoft Graph API (More Secure)

Instead of SMTP, you could use Microsoft Graph API with OAuth2, which is more secure and doesn't require SMTP AUTH. However, this requires more setup.

## Testing After Enabling

Once SMTP AUTH is enabled at the tenant level, run:
```powershell
cd "C:\Users\benmo\OneDrive\Documents\WWI ERP\backend_django"
.\venv\Scripts\python.exe test_email_connection.py
```

This will verify that the connection works.
