Batch Ticket Template Folder
=============================

Put your official Batch Ticket template here so the system can use the CANONICAL
template-filled version (exact layout, logo, pick list columns, etc.). Without a
template file here, the system falls back to a generic flowable PDF.

Supported files (first one found is used):
  - Batch_ticket_template.pdf / .docx / .doc
  - Batch Ticket template.pdf / .docx / .doc
  - Batch ticket template.pdf / .docx
  - Batch Ticket (BP-13).pdf / .docx / .doc
  - Batch Ticket.pdf, batch_ticket.pdf, BatchTicket.pdf

Note: Word lock files (names starting with ~$) are ignored. You must have the
actual template file (e.g. "Batch Ticket template.pdf") in this folder.

When a template is present and PyMuPDF is installed, the batch ticket generator:
  1. Uses your template as the base (layout, tables, checkboxes stay exactly as designed).
  2. Overlays only the variable data (Product ID, SKU, batch number, dates, pick list, etc.).

This folder is searched before the Sensitive/ folder. Requires: pip install pymupdf

You can also point to a different folder with an environment variable:
  set BATCH_TICKET_TEMPLATE_PATH=C:\Path\To\Your\Folder
  set BATCH_TICKET_TEMPLATE_DIR=C:\Path\To\Your\Folder
