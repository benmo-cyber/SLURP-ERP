# SLURP — Agent instructions

These instructions apply to all Agent (Chat) work in this repository.

## Django-first implementation

- Prefer **Django built-ins** over custom or third-party alternatives when they fit:
  - ORM and `QuerySet` APIs (avoid raw SQL unless necessary for migrations, drift repair, or documented performance needs)
  - `django.forms` / DRF serializers already used in the project
  - `django.contrib.auth`, permissions, and session/auth flows
  - `django.test.TestCase`, `TransactionTestCase`, and `django.test.Client` / DRF `APIClient` for tests
  - Management commands (`manage.py`) for one-off or operational tasks
  - Migrations for schema changes (defensive `RunPython` when SQLite drift is known)
- Do not introduce parallel frameworks (e.g. another ORM, ad-hoc routing, or bespoke auth) when Django already provides a supported path.
- Match existing patterns in `backend_django/erp_core/` before adding new abstractions.

## Unit tests (required for Python functions)

- For **each new or materially changed Python function** (module-level helpers, service functions, model methods, view logic extracted for testing), add a **unit test** using **`unittest`** via **`django.test.TestCase`** (or `SimpleTestCase` when the DB is not needed).
- Place tests under `backend_django/erp_core/tests/` (create the package if missing), named `test_<module>.py`, mirroring the module under test.
- Tests must be **deterministic**: no reliance on production data, external APIs, or wall-clock timing unless explicitly mocked.
- Run the relevant tests before considering work complete, e.g.:

  ```bash
  cd backend_django
  source .venv/bin/activate   # or project venv on the server
  python manage.py test erp_core.tests.test_<module> --settings=wwi_erp.settings
  ```

## Definition of done

- **Keep working on the task until all added/updated unit tests pass** (and existing tests in touched areas still pass).
- If a test fails, fix the implementation or the test for a real bug—do not delete or skip tests to greenwash the run.
- Do not mark a task complete after a single failed test run without attempting a fix.

## No hallucinations

- **Do not invent** APIs, model fields, migration names, file paths, env vars, systemd units, or AWS/infra details. **Read the codebase or config** first.
- If something is unknown (e.g. server paths, credentials, whether a table exists), **inspect** (`grep`, `read` files, `manage.py shell`, `PRAGMA table_info`, etc.) or **ask**—do not guess.
- Do not claim tests passed, migrations applied, or commands ran without actually running them in the environment you are using.
- Prefer citing real paths and symbols from this repo over generic examples.

## Project context (quick reference)

- **Backend:** `backend_django/` — Django, Python **3.12**, SQLite `wwi_erp.db` at repo root.
- **Frontend:** `frontend/` — Vite/React (separate from Django templates except PDF/HTML flows).
- **Local dev:** `backend_django/.venv`, `manage.py runserver`, `frontend/npm run dev`.
- **Production (AWS):** Gunicorn `gunicorn-slurp-erp`, nginx; DB may have migration/state drift—use repair patterns documented in migrations and `repair_invoice_tables` management command when applicable.
