# Private backups (not in Git)

This folder holds **exports of your real data** so you can push **code only** to Git and still move data to production later.

## Before you `git push` (after you finish legacy entry)

From `backend_django`:

```bash
python manage.py backup_erp_private_data
```

That creates a **timestamped `.zip`** here containing:

- `wwi_erp.db` — the SQLite file at the repo root (all ERP rows you typed in, plus Django users/sessions in that file)
- `media/` — uploaded files (PDFs, FPS uploads, etc.), if any

**Copy the zip somewhere safe** (another drive, S3, encrypted share). It is **ignored by Git**, so it will **not** upload when you push.

Optional — portable JSON (e.g. if production uses PostgreSQL later):

```bash
python manage.py backup_erp_private_data --json
```

## Sanity check

From the repo root:

```bash
git status
```

You should **not** see `wwi_erp.db`, anything under `media/`, or backup zips/JSON in this folder. Only **code** should be staged.

## Production (SQLite on the server)

1. Deploy code from Git; run `migrate`.
2. Stop the app.
3. Replace the server’s `wwi_erp.db` with the one from the zip (or unzip the whole bundle and place `wwi_erp.db` and `media/` per your server layout).
4. Start the app.

## Production (PostgreSQL or other DB)

Use a JSON export and `loaddata` only after reading Django’s docs — IDs and users differ from SQLite. When in doubt, keep using SQLite on the server until you plan a proper DB migration.
