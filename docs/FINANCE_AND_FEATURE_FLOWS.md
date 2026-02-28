# Finance and Feature Flows (How Each Flow Works)

## Invoicing → A/R → Journal Entry
When you **ship** a sales order (Check Out & Ship), the system creates an **Invoice** from the shipment and then calls `create_ar_entry_from_invoice(invoice)`. That creates an **Accounts Receivable** row (customer, due date, balance) and a **Journal Entry** (Debit AR, Credit Revenue), which is auto-posted. So: Ship → Invoice → AR entry + JE. Payments received later are recorded via Payments (AR payment), which create another JE (Debit Cash, Credit AR) and update the AR balance.

## A/P (Accounts Payable)
When a **Purchase Order** is received/invoiced, an AP entry can be created (manual or via integration). **Payments** (AP payment) record paying a vendor: they create a JE (Debit AP, Credit Cash) and update the AP entry’s amount_paid and balance.

## Period Close (Fiscal Periods)
**Fiscal periods** have an `is_closed` flag. When you **close a period** (Finance → Fiscal Periods → “Close period” or POST `/api/fiscal-periods/{id}/close/`), that period is locked. **No new journal entries** can be created or posted for that period: creating a JE with an entry_date in a closed period returns 400, and posting a JE in a closed period returns 400. Auto-created JEs (from AR, AP, payments) also skip creation if the period is closed.

## Bank Reconciliation
**Bank reconciliations** (Finance → Bank Reconciliation) record the **statement date** and **statement balance** for a bank account (e.g. Checking 1000). You add a row per statement; this does not auto-match to GL. It’s for recording what the bank says so you can compare to the GL balance (e.g. on General Ledger or Trial Balance for that account).

## P&L, Trial Balance, Balance Sheet, Cash Flow
**Financial Reports** and **P&L Actual / P&L Pro-Forma** use **fiscal period** (or date range) and read from **General Ledger** and **Account Balances**. Posted journal entries drive GL and period balances; reports aggregate by account type (revenue, expense, asset, liability, equity) for the chosen period.

## AR / AP Aging
**AR** and **AP** list open/partial entries; **aging** is computed from `due_date` (e.g. 0–30, 31–60, 61–90, 90+ days). The backend exposes aging buckets; the frontend can show “View Aging Report” using the existing AR/AP aging APIs.

## What Was Added in This Pass
- **Period close**: Fixed `FiscalPeriod` `get_or_create` (use `period_name`; removed invalid `period_type`). Enforced: no create/post JE in closed period; close action on FiscalPeriodViewSet. Frontend: **Fiscal Periods** tab with list and “Close period”.
- **Bank reconciliation**: Model `BankReconciliation` (account, statement_date, statement_balance, reconciled_at, notes), API (CRUD), migration, and **Bank Reconciliation** tab in Finance (list + add).
- **Flows doc**: This file.

## What Exists Already (Use, Don’t Duplicate)
- Invoice → AR → JE (on ship).
- Payment → AP/AR update + JE.
- Fiscal periods, journal entries, general ledger, account balances.
- AR/AP aging APIs (`/accounts-receivable/aging/`, `/accounts-payable/aging/`).
- Financial reports (trial balance, balance sheet, income statement, cash flow), P&L Actual, P&L Pro-Forma.
- Chart of accounts (e.g. 1000 Checking, 1100 AR, 2000 AP, 4000 Revenue, 5000 expense).

## Nice-to-Have Not Yet Implemented
- **COGS/margin by order**: Report or field per invoice/SO line using CostMaster or batch cost.
- **Role-based access**: Restrict posting (e.g. only “finance” can post JE or close period); Django auth exists but no permission checks on these views yet.
- **Purchase requisitions**: Req → PO workflow (model + API + UI not added).
- **MRP/demand**: Simplified “demand” report from SO + production schedule (not added).
- **Multi-currency**: Currency on Invoice/SO/PO and display (not added).
- **Audit log**: Generic log of key actions (create/update/delete on JE, Invoice, AR, AP, etc.) for compliance (not added).
