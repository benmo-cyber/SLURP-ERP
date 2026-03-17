# Backdated Entry (Staff)

Trusted users (staff/superuser) can enter data with **past dates** for testing or loading historical data before going to production.

## How it works

- **Backend**: When creating or updating lots (e.g. check-in), the API accepts any valid `received_date` (and other date fields). There is no server-side restriction to "today" for these fields. Staff can send `received_date`, `production_date`, `ship_date`, etc. as needed.
- **Frontend**: If a form restricts date pickers to today (e.g. `max={today}`), staff can:
  - Use the API directly (e.g. Postman) with past dates, or
  - Enable a "Backdated entry" mode in the app (if implemented) so date inputs allow any date.

## Reconcile (admin override)

Staff can correct inventory when reality and system diverge:

- **Inventory → Lot breakdown → Reconcile**: Set `quantity_remaining` to the physical count and optionally enter a reason. The action is logged in Lot Transaction Log with type `adjustment` and `reference_type=admin_reconcile`.
- **API**: `POST /api/lots/{id}/reconcile/` with body `{ "quantity_remaining": number, "reason": "string" }`. Requires staff or superuser.

## Testing with historical data

To load or correct data from previous dates:

1. Use **Reconcile** to fix current quantities.
2. For new check-ins with a past received date: call the lot create/check-in API with the desired `received_date` (e.g. from a script or Postman), or use the UI if date inputs allow past dates when in backdated mode.
