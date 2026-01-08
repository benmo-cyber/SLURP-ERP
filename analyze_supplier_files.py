import xlrd
import os
from pathlib import Path

# Read the Excel file
print("=" * 80)
print("ANALYZING WWI SUPPLIER QUALITY SURVEY")
print("=" * 80)

try:
    workbook = xlrd.open_workbook('Supplier_Approval_Monitoring/WWI Supplier Quality Survey.xls')
    sheet_names = workbook.sheet_names()
    print(f"\nTotal Sheets: {len(sheet_names)}")
    print(f"Sheet Names: {sheet_names}\n")
    
    for sheet_name in sheet_names:
        sheet = workbook.sheet_by_name(sheet_name)
        print(f"\n{'=' * 80}")
        print(f"SHEET: {sheet_name}")
        print(f"{'=' * 80}")
        print(f"Dimensions: {sheet.nrows} rows x {sheet.ncols} columns\n")
        
        # Read first 50 rows
        for row_idx in range(min(50, sheet.nrows)):
            row_data = []
            for col_idx in range(sheet.ncols):
                cell = sheet.cell(row_idx, col_idx)
                if cell.ctype == xlrd.XL_CELL_NUMBER:
                    row_data.append(cell.value)
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    row_data.append(xlrd.xldate_as_datetime(cell.value, workbook.datemode))
                else:
                    row_data.append(str(cell.value).strip())
            
            # Only print non-empty rows
            if any(str(cell).strip() for cell in row_data if cell):
                print(f"Row {row_idx + 1}: {row_data}")
        
        if sheet.nrows > 50:
            print(f"\n... ({sheet.nrows - 50} more rows)")
            
except Exception as e:
    print(f"Error reading Excel: {e}")

# List PDF files
print("\n\n" + "=" * 80)
print("PDF FILES FOUND")
print("=" * 80)
pdf_files = [
    "Supplier Approval & Monitoring Policy (3.5.1.1 - 01).pdf",
    "Supplier Approval & Monitoring Procedure (3.5.1.1 - 02).pdf",
    "Packaging Supplier Approval & Monitoring Procedure - (3.5.5.1.3 -01).pdf",
    "Service Provider Approval & Monitoring Procedure (3.5.3.1 - 01).pdf",
    "Supplier Documentation Request (3.5 - 02).pdf",
    "Supplier Survey Review Form - (3.5.1.1 - 05).pdf",
    "Temporary Supplier Exception Form (3.5.1.1 - 04).pdf"
]

for pdf in pdf_files:
    path = f"Supplier_Approval_Monitoring/{pdf}"
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"[OK] {pdf} ({size:,} bytes)")
    else:
        print(f"[MISSING] {pdf} (not found)")

