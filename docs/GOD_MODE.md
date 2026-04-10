# God mode (staff)

**God mode** is a staff-only toggle in the app header. When enabled:

- Date inputs are **not** limited to today (`max` / `min` on `<input type="date">` are relaxed) so you can enter **any** historical or future date where the UI supports it.
- Key flows accept **custom business dates** on the API when you are **`is_staff`** (e.g. PO issue date, SO issue / order date, PO received date).

## Enabling

1. Sign in as **staff** or **superuser**.
2. Check **God mode** in the header.

Your choice is stored in `localStorage` under `erp_god_mode`. If you previously used **Backdated entry**, that setting is migrated once from `erp_backdated_entry`.

## Document numbers (PO / SO / invoice)

With **God mode** on, staff can change **PO number** (purchase order detail), **SO number** (edit sales order), and **invoice number** (invoice detail while editing). The API requires **`is_staff`**; duplicate numbers are rejected.

## Server rules

Custom dates on issue/receive endpoints are **rejected for non-staff** (`403`). The UI only shows God mode to staff.

## Related code

- Frontend: `frontend/src/context/GodModeContext.tsx`
- Examples: PO issue/receive (`PurchaseOrderViewSet`), SO issue/create (`SalesOrderViewSet`)
