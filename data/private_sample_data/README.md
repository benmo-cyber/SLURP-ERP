# Private sample / legacy data (not committed)

Put one or more `.xml` files here. They are **ignored by Git** so you can push code without your legacy dumps.

## Format

See the committed template at **`data/sample_import_template.xml`** (repo root). Copy it here and edit, or generate your own XML that matches that structure.

## Load into the app

**Option A — UI (staff):** Sign in as a staff user → use **Import sample XML** in the header (runs all `.xml` files in this folder).

**Option B — CLI:**

```bash
cd backend_django
python manage.py import_private_sample_xml
```

After import, open **Inventory → Items**, **Sales** (customers), or **Quality → Vendors** to see records.
