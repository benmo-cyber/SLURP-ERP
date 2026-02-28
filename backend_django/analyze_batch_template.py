"""
One-off script to extract pick list positions from Batch ticket template.pdf.
Run from backend_django: python analyze_batch_template.py
"""
import sys
from pathlib import Path

# Template in project root
project_root = Path(__file__).resolve().parent.parent
template_path = project_root / "Batch ticket template.pdf"
if not template_path.exists():
    print(f"Template not found: {template_path}")
    sys.exit(1)

try:
    import fitz
except ImportError:
    print("Install pymupdf: pip install pymupdf")
    sys.exit(1)

doc = fitz.open(template_path)
page = doc[0]
page_height = page.rect.height
# Page 2 (index 1): Pack off table
if len(doc) > 1:
    page2 = doc[1]
    blocks2 = page2.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
    print("\n--- Page 2 text (Pack off area) ---")
    for block in blocks2:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = (span.get("text") or "").strip()
                if not t:
                    continue
                bbox = span.get("bbox")
                if bbox:
                    x0, y0, x1, y1 = bbox
                    safe_t = t[:60].encode("ascii", "replace").decode("ascii")
                    print(f"  y={y0:.1f}  x={x0:.1f}-{x1:.1f}  {repr(safe_t)}")
                    if "pack" in t.lower() or "packaging" in t.lower() or "lot" in t.lower() or "qty" in t.lower() or "off" in t.lower():
                        print(f"    ^^^ PACK OFF RELATED")
page_width = page.rect.width
print(f"Page size: {page_width} x {page_height} pt")
print(f"(PyMuPDF: origin top-left, y increases downward)\n")

# Get all text with positions
blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
print("--- All text blocks (looking for pick list headers) ---")
for bi, block in enumerate(blocks):
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = (span.get("text") or "").strip()
            if not t:
                continue
            bbox = span.get("bbox")
            if bbox:
                x0, y0, x1, y1 = bbox
                # y from top in PyMuPDF
                safe_t = t[:50].encode("ascii", "replace").decode("ascii")
                print(f"  y={y0:.1f}  x={x0:.1f}-{x1:.1f}  {repr(safe_t)}")
            if "raw" in t.lower() or "material" in t.lower() or "quantity" in t.lower() or "qty" in t.lower() or "vendor" in t.lower() or "pick" in t.lower():
                print(f"    ^^^ PICK LIST RELATED")

print("\n--- Suggested pick list values ---")
# Find first row y: look for "Raw Material" or "Quantity" or similar
header_y = None
col_raw = col_sku = col_vendor = col_vendor_lot = col_qty = col_pick = col_prod = None
for block in blocks:
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            t = (span.get("text") or "").strip().lower()
            bbox = span.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            if "raw material" in t:
                col_raw = x0
                header_y = max(header_y or 0, y1)
            if "sku" in t and "raw" not in t:
                col_sku = x0
                header_y = max(header_y or 0, y1)
            if "vendor" in t and "lot" not in t:
                col_vendor = x0
                header_y = max(header_y or 0, y1)
            if "vendor lot" in t or ("vendor" in t and "lot" in t):
                col_vendor_lot = x0
                header_y = max(header_y or 0, y1)
            if "quantity" in t or t == "qty":
                col_qty = x0
                header_y = max(header_y or 0, y1)
            if "pick initial" in t:
                col_pick = x0
                header_y = max(header_y or 0, y1)
            if "production initial" in t:
                col_prod = x0
                header_y = max(header_y or 0, y1)

if header_y is not None:
    # First data row: typically a bit below header
    first_row_y = header_y + 18
    print(f"Header bottom y (from top): {header_y:.1f}")
    print(f"Suggested first data row top: {first_row_y:.1f}")
    print(f"Suggested first data row baseline (~+10): {first_row_y + 10:.1f}")
print("Column left edges (x from left):")
for name, val in [("raw_material", col_raw), ("sku", col_sku), ("vendor", col_vendor), ("vendor_lot", col_vendor_lot), ("qty", col_qty), ("pick_init", col_pick), ("prod_init", col_prod)]:
    if val is not None:
        print(f"  {name}: {val:.1f} pt  ({val/72:.2f} in)")
    else:
        print(f"  {name}: (not found)")

# Build list like _P1_PICK_COLS in inches
found = [col_raw, col_sku, col_vendor, col_vendor_lot, col_qty, col_pick, col_prod]
if all(f is not None for f in found):
    in_inches = [round(f / 72, 2) for f in found]
    print(f"\nPython list (inches) for _P1_PICK_COLS: {in_inches}")
    print(f"Python list (pt): {[round(f) for f in found]}")

# Get drawings (lines) to find table row boundaries
print("\n--- Horizontal lines (y positions) in pick list area (y 150-400) ---")
try:
    drawings = page.get_drawings()
    y_positions = set()
    for d in drawings:
        rect = d.get("rect")
        items = d.get("items", [])
        if rect:
            y_positions.add(round(rect.y0, 1))
            y_positions.add(round(rect.y1, 1))
        for item in items:
            if item[0] == "l":  # line
                p1, p2 = item[1], item[2]
                y_positions.add(round(p1[1], 1))
                y_positions.add(round(p2[1], 1))
            elif item[0] == "re":  # rect
                x0, y0, x1, y1 = item[1]
                y_positions.add(round(y0, 1))
                y_positions.add(round(y1, 1))
    for y in sorted(y_positions):
        if 150 <= y <= 400:
            print(f"  y={y}")
except Exception as e:
    print(f"  (drawings error: {e})")

doc.close()
print("\nDone.")
