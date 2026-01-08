try:
    from pypdf import PdfReader
    import sys
    
    pdf_files = [
        "Supplier_Approval_Monitoring/Supplier Approval & Monitoring Policy (3.5.1.1 - 01).pdf",
        "Supplier_Approval_Monitoring/Supplier Approval & Monitoring Procedure (3.5.1.1 - 02).pdf",
        "Supplier_Approval_Monitoring/Service Provider Approval & Monitoring Procedure (3.5.3.1 - 01).pdf",
        "Supplier_Approval_Monitoring/Supplier Documentation Request (3.5 - 02).pdf",
        "Supplier_Approval_Monitoring/Supplier Survey Review Form - (3.5.1.1 - 05).pdf",
        "Supplier_Approval_Monitoring/Temporary Supplier Exception Form (3.5.1.1 - 04).pdf"
    ]
    
    for pdf_path in pdf_files:
        try:
            print("\n" + "=" * 80)
            print(f"FILE: {pdf_path.split('/')[-1]}")
            print("=" * 80)
            reader = PdfReader(pdf_path)
            print(f"Pages: {len(reader.pages)}\n")
            
            # Extract first 3 pages of text
            for i, page in enumerate(reader.pages[:3], 1):
                text = page.extract_text()
                if text.strip():
                    print(f"--- Page {i} ---")
                    # Print first 2000 characters
                    print(text[:2000])
                    if len(text) > 2000:
                        print("... (more content)")
                    print()
        except Exception as e:
            print(f"Error reading {pdf_path}: {e}")
            
except ImportError:
    print("pypdf not available, trying PyPDF2...")
    try:
        import PyPDF2
        # Similar extraction logic with PyPDF2
    except:
        print("No PDF library available")

