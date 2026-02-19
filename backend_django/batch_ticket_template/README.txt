Batch Ticket Template Folder
=============================

Put your official Batch Ticket template here so the system can use it.

Supported files (first one found is used):
  - Batch_ticket_template.docx / .doc / .pdf
  - Batch Ticket template.pdf / .docx / .doc
  - Batch Ticket (BP-13).pdf / .docx / .doc
  - Batch Ticket.pdf, batch_ticket.pdf, BatchTicket.pdf

When you place a PDF or Word file here, the batch ticket generator will:
  1. Use your template as the base (layout, tables, checkboxes stay exactly as designed).
  2. Overlay only the variable data (Product ID, SKU, batch number, dates, pick list, etc.) on top.

This folder is searched before the Sensitive/ folder, so you can keep the template here and commit it to the repo if you want.

You can also point to a different folder with an environment variable:
  set BATCH_TICKET_TEMPLATE_PATH=C:\Path\To\Your\Folder
  set BATCH_TICKET_TEMPLATE_DIR=C:\Path\To\Your\Folder
