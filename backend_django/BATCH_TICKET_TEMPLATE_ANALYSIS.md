# Batch Ticket: Template vs System — Analysis and Alignment

## Approach

1. **When the template file exists** (`Sensitive/Batch Ticket template.pdf` or `.docx`):  
   The template PDF is used as the base. The system builds a **transparent overlay** that draws **only variable data** (Product ID, SKU, Batch Number, Batch Size, Pack Size, Production Date, Pick List rows, Pack Off rows, Yield/Loss/Spill/Waste, QC data). The overlay is merged on top of the template so the template’s exact **structure, flow, design, placement, tables, headers, and checkboxes** are preserved.

2. **When no template is found or merge fails**:  
   A **flowable PDF** is built to mirror the template: same order of sections, header as a label/value table, Pre-Production as a table with Yes/No-style columns, Batch Instructions and Pick List tables, and matching page 2 layout.

## Template structure (from Batch Ticket template.pdf)

### Page 1
- **Batch Ticket** (title)
- **Product ID:** [value]
- **SKU:** [value]
- **Batch Number:** [value]
- **Batch Size:** [value] **Pack Size:** [value]
- Confidentiality paragraph (static)
- **Batch Ticket – Updated 02/06/2026 (GDM) – … (BP-13)** (static)
- **Production Date:**  
  [value or line]
- **Pre-Production Checks** … **Start Time ____________**
- **Equipment Sanitized and in good order?**  
  Yes | No | Campaign | Operator Initials ___ | Supervisor Initials ___
- **Has 20 mesh screen been inspected and installed properly?**  
  Yes | No | Operator Initials ___ | Supervisor Initials ___
- **Batch Instructions**  
  Table: Step | Initial After Completion; rows 1.)–6.) with **End Time ____________** on row 6
- **Pick List**  
  **Pick Date___________** **Start Time _________ End Time___________**  
  Table: Raw Material SKU | Vendor | Vendor Lot | Quantity | Pick Initials | Production Initials | Wildwood Lot
- **-- 1 of 2 --**

### Page 2
- **Batch Ticket** (title)
- Same header block (Product ID, SKU, Batch Number, Batch Size, Pack Size)
- Same confidentiality and BP-13 footer
- **Post-Production Checks** … **Start Time ____________**
- **Screen Clean of Extraneous Foreign Material?**  
  Yes | No | If No, Explain: ________________
- **Operator Initials _____________ Supervisor Initials _______________**
- **Pack Off**  
  Table: Packaging | Lot | Quantity | Pick Initial | Pack Initial | Amount Unused & Returned to Inventory
- *Enter (+) when adding unused packaging…
- **Yield:** ___ **Loss:** ___ **End Time ____________**
- **Spill** ___ **Waste** ___
- I confirm that all information…
- **Production Signature** **Date** / line / **Supervisor Verification** **Date** / line
- **QC Results (Please write all data): Start Time _________ Initials __________**
- **Adjustments (If needed):** / Raw Materials added…
- **QC Disposition:** / Approve | Not Approved / **Initials: ________________**
- If QC does not approve… **End Time ____________**
- **-- 2 of 2 --**

## Overlay coordinates (template path)

Positions are in inches (from bottom-left). They are tuned so that overlay text sits in the template’s blank areas; they can be adjusted if your template layout differs.

- **Page 1:** Product ID, SKU, Batch Number, Batch Size, Pack Size, Production Date, Pick List table (columns and row start height), logo, page number.
- **Page 2:** Same header block, Pack Off table, Yield/Loss/Spill/Waste, QC data, page number.

See `_P1_*` and `_P2_*` constants in `batch_ticket_pdf.py` for exact values.

## Differences addressed

- **Confidentiality:** Template has it immediately after the header block; overlay does not draw it (it stays from the template).
- **Pick list:** Template has a fixed table layout; overlay draws only the data rows at the defined column positions.
- **Checkboxes:** Template’s Yes/No and other boxes are part of the template; overlay does not draw over them.
- **Flowable fallback:** Header is a label/value table; Pre-Production uses a table with Yes/No-style columns; order and wording follow the template.
