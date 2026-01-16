"""
Load Chart of Accounts from the provided structure.
This script should be run once to populate the chart of accounts.
Accounts created by this script are protected from test data clearing.
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import Account

# Chart of Accounts structure
# Format: (account_number, name, account_type, description, parent_account_number)
CHART_OF_ACCOUNTS = [
    # ASSETS (1000-1690)
    ('1000', 'Checking Account', 'asset', 'Main operating bank account', None),
    ('1010', 'Savings Account', 'asset', '', None),
    ('1100', 'Accounts Receivable', 'asset', '', None),
    ('1200', 'Inventory Assets', 'asset', 'Summary total', None),
    ('1210', 'Raw Materials Inventory', 'asset', 'Imported inputs', '1200'),
    ('1220', 'Natural Color Inventory', 'asset', 'Finished goods (natural)', '1200'),
    ('1230', 'Synthetic Color Inventory', 'asset', 'Finished goods (synthetic)', '1200'),
    ('1240', 'Antioxidant Inventory', 'asset', 'Finished goods (antioxidant)', '1200'),
    ('1250', 'Packaging Inventory', 'asset', 'Bottles, drums, labels', '1200'),
    ('1300', 'Landed Cost Clearing Account', 'asset', 'Freight/duties/tariffs before capitalization', None),
    ('1400', 'Prepaid Expenses', 'asset', 'Annual insurance, certifications', None),
    ('1500', 'Tax Holding Account', 'asset', 'Reserve for tax liabilities', None),
    ('1600', 'Equipment', 'asset', 'Parent account', None),
    ('1610', 'Production Equipment', 'asset', 'Mixers, scales, production tools', '1600'),
    ('1620', 'Office Equipment', 'asset', 'Computers, desks, furniture', '1600'),
    ('1630', 'Lab Equipment', 'asset', 'Colorimeter, beakers, glassware', '1600'),
    ('1690', 'Accumulated Depreciation', 'asset', 'Contra-asset for equipment', '1600'),
    
    # LIABILITIES (2000-2500)
    ('2000', 'Accounts Payable', 'liability', 'Vendor payables', None),
    ('2110', 'Federal Taxes Payable', 'liability', 'Payroll liabilities', None),
    ('2120', 'Federal Unemployment Tax', 'liability', '', None),
    ('2130', 'Missouri Income Tax', 'liability', '', None),
    ('2140', 'Missouri Unemployment Tax', 'liability', '', None),
    ('2200', 'Accrued Tariffs / Customs Payable', 'liability', 'Payable to CBP monthly', None),
    ('2300', 'Line of Credit Payable', 'liability', 'Commerce Bank LOC', None),
    ('2400', 'Long-Term Loan', 'liability', 'Equipment financing', None),
    ('2500', 'Due to Employees', 'liability', 'Reimbursements clearing account', None),
    
    # EQUITY (3000-3200)
    ('3000', "Owner's Equity", 'equity', 'Capital contributions', None),
    ('3100', 'Owner Draws', 'equity', 'Withdrawals / personal expenses', None),
    ('3200', 'Retained Earnings', 'equity', 'Auto-calculated by QBO', None),
    
    # REVENUE (4000-4100)
    ('4000', 'Sales - Finished Goods', 'revenue', 'Parent income account', None),
    ('4010', 'Natural Color Sales', 'revenue', '', '4000'),
    ('4020', 'Synthetic Color Sales', 'revenue', '', '4000'),
    ('4030', 'Antioxidant Sales', 'revenue', '', '4000'),
    ('4100', 'Other Primary Income', 'revenue', 'Freight recovery, misc income', None),
    
    # EXPENSES (5000-7130)
    ('5000', 'Raw Materials Used', 'expense', 'Monthly consumption', None),
    ('5100', 'Freight-in / Import Freight', 'expense', '', None),
    ('5200', 'Customs, Duties & Tariffs', 'expense', '', None),
    ('5300', 'Manufacturing Loss / Shrinkage', 'expense', 'Yield loss from blending', None),
    ('5400', 'Packaging Supplies', 'expense', '', None),
    ('5500', 'Subcontract / Blending Labor', 'expense', 'Outside processing', None),
    ('5600', 'Inventory Adjustments', 'expense', 'Manual corrections', None),
    ('6000', 'Payroll Expenses', 'expense', 'Parent account', None),
    ('6010', 'Payroll Taxes', 'expense', 'Employer portion', '6000'),
    ('6020', 'Wages', 'expense', 'Employee pay', '6000'),
    ('6100', 'Rent / Utilities', 'expense', 'Facility costs', None),
    ('6200', 'Office Supplies', 'expense', 'Administrative supplies', None),
    ('6300', 'Professional Fees', 'expense', 'CPA, legal, consultants', None),
    ('6400', 'Travel & Meals', 'expense', 'Parent account', None),
    ('6410', 'Travel Expense', 'expense', 'Airfare, lodging, mileage', '6400'),
    ('6415', 'Travel - Employee Meals', 'expense', '50% deductible', '6400'),
    ('6420', 'Meals - Business', 'expense', 'Client/vendor meals', '6400'),
    ('6430', 'Entertainment - Non-Deductible', 'expense', '', '6400'),
    ('6500', 'Shipping', 'expense', 'Parent account', None),
    ('6510', 'Shipping to Customers', 'expense', '', '6500'),
    ('6520', 'Shipping for Samples', 'expense', '', '6500'),
    ('6600', 'Bank & Credit Card Fees', 'expense', '', None),
    ('6700', 'Software / Subscriptions', 'expense', '', None),
    ('6800', 'Marketing / Promotion', 'expense', '', None),
    ('6900', 'Interest Expense', 'expense', 'Parent account', None),
    ('6910', 'Interest - Line of Credit', 'expense', '', '6900'),
    ('6920', 'Interest - Equipment Loan', 'expense', '', '6900'),
    ('6990', 'Miscellaneous Expense', 'expense', '', None),
    ('7000', 'Insurance Expense', 'expense', 'Parent account', None),
    ('7100', 'Quality & Compliance', 'expense', 'Parent account', None),
    ('7110', 'Kosher Certification Fees', 'expense', '', '7100'),
    ('7120', 'Food Safety / BRC Audits', 'expense', '', '7100'),
    ('7130', 'Product Testing & Lab Fees', 'expense', '', '7100'),
]


def load_chart_of_accounts():
    """Load all accounts from the chart of accounts structure."""
    created_count = 0
    updated_count = 0
    skipped_count = 0
    
    # First pass: Create all accounts without parent relationships
    accounts_dict = {}
    for account_number, name, account_type, description, parent_account_number in CHART_OF_ACCOUNTS:
        account, created = Account.objects.get_or_create(
            account_number=account_number,
            defaults={
                'name': name,
                'account_type': account_type,
                'description': description or '',
                'is_active': True,
            }
        )
        
        if created:
            created_count += 1
            print(f"Created account: {account_number} - {name}")
        else:
            # Update existing account if needed
            updated = False
            if account.name != name:
                account.name = name
                updated = True
            if account.account_type != account_type:
                account.account_type = account_type
                updated = True
            if account.description != (description or ''):
                account.description = description or ''
                updated = True
            if not account.is_active:
                account.is_active = True
                updated = True
            
            if updated:
                account.save()
                updated_count += 1
                print(f"Updated account: {account_number} - {name}")
            else:
                skipped_count += 1
                print(f"Skipped (already exists): {account_number} - {name}")
        
        accounts_dict[account_number] = account
    
    # Second pass: Set parent relationships
    parent_updated_count = 0
    for account_number, name, account_type, description, parent_account_number in CHART_OF_ACCOUNTS:
        if parent_account_number:
            account = accounts_dict[account_number]
            parent_account = accounts_dict.get(parent_account_number)
            
            if parent_account and account.parent_account != parent_account:
                account.parent_account = parent_account
                account.save()
                parent_updated_count += 1
                print(f"Set parent for {account_number} -> {parent_account_number}")
    
    print("\n" + "="*60)
    print("Chart of Accounts Loading Summary:")
    print(f"  Created: {created_count}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Parent relationships set: {parent_updated_count}")
    print(f"  Total accounts: {len(CHART_OF_ACCOUNTS)}")
    print("="*60)
    
    return {
        'created': created_count,
        'updated': updated_count,
        'skipped': skipped_count,
        'parent_relationships': parent_updated_count,
        'total': len(CHART_OF_ACCOUNTS)
    }


if __name__ == '__main__':
    print("Loading Chart of Accounts...")
    print("="*60)
    result = load_chart_of_accounts()
    print("\nChart of Accounts loaded successfully!")
