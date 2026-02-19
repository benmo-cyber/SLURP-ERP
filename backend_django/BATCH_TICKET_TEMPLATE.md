# Batch Ticket Template — Copy the template EXACTLY

When a template is present and **PyMuPDF** is installed (`pip install pymupdf`), the system opens your template PDF and inserts only the variable data at the template’s label positions. The result is an **exact copy** of your template. Without PyMuPDF, a flowable PDF is generated instead.

<!-- the template’s layout, tables, and checkboxes are kept; only variable data is overlaid. -->

## Template location (search order)

1. **Environment variable**  
   `BATCH_TICKET_TEMPLATE_PATH` or `BATCH_TICKET_TEMPLATE_DIR` — path to a specific file or to a folder to search.

2. **Project folder (recommended)**  
   Put the template in:
   ```
   backend_django/batch_ticket_template/
   ```
   e.g. `Batch Ticket template.pdf`. This folder is in the project so the template can be committed and the path is reliable.

3. **Sensitive folder**  
   `WWI ERP/Sensitive/` (gitignored).

The generator looks for the first existing file among:

- Batch Ticket template.pdf / .docx / .doc  
- Batch Ticket (BP-13).pdf / .docx / .doc  
- Batch Ticket.pdf, batch_ticket.pdf, BatchTicket.pdf

## How it is used

- **When the template exists:** The template is converted to PDF if it’s a Word document, then the **first page** is prepended to every generated batch ticket. So the exact file, format and layout of that template become the first page of each printed batch ticket; dynamic data (batch number, inputs, outputs, QC, etc.) follows on the next pages.
- **When no template is found:** The generator still produces a full batch ticket with all sections (BATCH TICKET, INPUT MATERIALS, OUTPUT LOTS, QUALITY CONTROL) on dynamically generated pages.

## Dependencies

- **pypdf** – used to merge the template’s first page with the generated PDF:
  ```bash
  pip install pypdf
  ```

- **Word template (.docx) conversion (pick one):**
  - **Windows:** **docx2pdf** (uses Microsoft Word via COM to convert .docx to PDF):
    ```bash
    pip install docx2pdf
    ```
  - **Any OS:** Install **LibreOffice**. The generator will use headless conversion:
    ```bash
    soffice --headless --convert-to pdf "Batch Ticket (BP-13).docx"
    ```

If pypdf is not installed, the generator still runs but does not merge the template page. If neither docx2pdf nor LibreOffice is available, a Word template will not be merged (PDF templates still work).
