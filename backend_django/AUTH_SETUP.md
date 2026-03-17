# SLURP authentication setup

## First-time: create a user

1. Create a Django user (e.g. superuser):
   ```bash
   cd backend_django
   python manage.py createsuperuser
   ```
   Enter username, email, and password.

2. Assign an ERP role:
   - Open Django admin: http://localhost:8000/admin/
   - Log in with the same user.
   - Go to **ERP Core → User profiles**.
   - Add a **User profile** for your user and set **Role** to one of:
     - **Viewer** – read-only
     - **Operator** – can perform day-to-day operations
     - **Manager** – broader access
     - **Admin** – full access

3. Log in to the app at http://localhost:5173 (or your frontend URL) with that username and password.

## Password reset

- Users use **Forgot password?** on the login page.
- They enter their email; if it exists, they receive a reset link (uses your `EMAIL_*` and `FRONTEND_URL` settings).
- The link goes to the frontend `/reset-password?uid=...&token=...`; they set a new password there.

## Roles (license tiers)

| Role     | Description |
|----------|-------------|
| Viewer   | Read-only access to data. |
| Operator | Can perform transactions (e.g. check-in, production, sales). |
| Manager  | Operator + higher-level actions (config, approvals). |
| Admin    | Full access; can manage users and roles in Django admin. |

Role checks are in place via `erp_core.permissions`; the API requires an authenticated user by default. You can restrict specific views or actions by role by adding permission classes to those viewsets.
