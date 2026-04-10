# Backend Python runtime (PO HTML PDF / xhtml2pdf)

**Use Python 3.12 for the Django backend.** Python 3.14 (and sometimes bleeding-edge runtimes) can cause `xhtml2pdf` to hang when generating PO PDFs.

## One-time setup (Windows)

1. Install **Python 3.12** if needed (you should see it in `py -0p` as `-V:3.12`).
2. **Ensure pip exists for 3.12** — run `py -3.12 -m pip --version`. If you see `No module named pip`, some winget/store builds omit pip. Fix:

   ```powershell
   Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile "$env:TEMP\get-pip.py"
   py -3.12 "$env:TEMP\get-pip.py"
   ```

   Or reinstall from [python.org](https://www.python.org/downloads/) and enable **pip** in the installer.

3. Create a **virtualenv outside OneDrive** (OneDrive can lock `python.exe` inside the repo and break venv/pip):

   ```powershell
   py -3.12 -m venv "$env:LOCALAPPDATA\wwi-erp-backend-venv"
   & "$env:LOCALAPPDATA\wwi-erp-backend-venv\Scripts\python.exe" -m pip install --upgrade pip
   & "$env:LOCALAPPDATA\wwi-erp-backend-venv\Scripts\python.exe" -m pip install -r requirements.txt
   ```

4. Run the API with that interpreter:

   ```powershell
   cd path\to\backend_django
   & "$env:LOCALAPPDATA\wwi-erp-backend-venv\Scripts\python.exe" manage.py runserver
   ```

   Or use the helper script: `.\run-server.ps1` (same venv path).

## Verify

```powershell
& "$env:LOCALAPPDATA\wwi-erp-backend-venv\Scripts\python.exe" -c "import sys; import xhtml2pdf; print(sys.version)"
```

You should see a 3.12.x version line.

## PDF architecture (unified)

Business PDFs (PO, invoice, sales order confirmation, packing list, batch ticket, **finished product specification / FPS**) are generated with **HTML templates + xhtml2pdf**, using the shared helper `erp_core/html_pdf_common.py` (subprocess + timeout). There is no ReportLab / PyMuPDF / Word-template fallback for those flows in the API.
