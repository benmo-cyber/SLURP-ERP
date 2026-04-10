# SLURP

**Current Version - Latest Build**

This is the current and only version of SLURP. When asked to "pull up SLURP", this is the version to use.

## System Information

- **System Name**: SLURP
- **Version**: Current/Latest
- **Status**: Active Development
- **Location**: This directory contains the complete SLURP system

## Daily Workflow

### Ending Your Day:
1. **Save All Files**: Press `Ctrl+K, S` (or File → Save All) to save all open files
2. **Commit Your Work**: Run these commands in the terminal:
   ```bash
   git add .
   git commit -m "End of day - [describe what you worked on]"
   ```

### Starting Your Day:
1. Check what changed: `git status`
2. View your work history: `git log --oneline`

### Going Back to a Previous Version:
```bash
# See all your commits
git log

# Go back to a specific commit (replace COMMIT_ID with actual ID)
git checkout COMMIT_ID

# Or go back to yesterday's work
git log --since="yesterday"
```

## Important Notes:

- **This is the canonical version** - This directory contains the one and only current version of SLURP
- **Database auto-saves** - Your data is always safe
- **Code files need to be saved manually** - When I make changes, you need to save them:
  - Press `Ctrl+K, S` (or File → Save All) to save all open files
  - Or use File → Save All from the menu
  - **You do NOT need to tell me to save** - just save the files yourself before closing Cursor
- **Git tracks your code** - You can now go back to any previous version
- **Database is NOT in Git** - It's in `.gitignore` to keep it safe

## Backend (Django) Python version

PO PDF generation uses **xhtml2pdf**, which is unreliable on **Python 3.14**. Run the API on **Python 3.12** — see `backend_django/PYTHON_RUNTIME.md` and `backend_django/run-server.ps1`.

## Quick Commands:

- `git status` - See what files changed
- `git add .` - Stage all changes
- `git commit -m "message"` - Save a snapshot
- `git log` - See your history

## Start both servers (Django + frontend)

From the repo root in PowerShell:

```powershell
.\scripts\start-slurp-dev.ps1
```

This opens two windows: `backend_django\run-server.ps1` (Python 3.12 venv) and `npm run dev` in `frontend/`.

## Vendor addresses (list + detail)

The API adds **`display_address`** on each vendor (built from street/city/legacy `address` and supplier survey JSON). The Vendor Approval table and vendor Overview use this.

**After pulling code changes**, restart the Django process (stop the backend window and run `.\scripts\start-slurp-dev.ps1` or `backend_django\run-server.ps1` again), then hard-refresh the browser (**Ctrl+F5**).

**Optional — copy survey JSON into Vendor columns** (for POs/PDFs that only read the `Vendor` model):

```powershell
cd backend_django
# Use the same Python as run-server.ps1 (venv), e.g.:
#   & "$env:LOCALAPPDATA\wwi-erp-backend-venv\Scripts\python.exe" manage.py sync_vendor_address_from_survey --dry-run
py -3.12 manage.py sync_vendor_address_from_survey --dry-run
py -3.12 manage.py sync_vendor_address_from_survey
```





