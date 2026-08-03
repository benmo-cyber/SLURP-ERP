# SLURP 2.0 — Django template port report

**Branch:** `SLURP-2.0`  
**Approach:** Django views + server-rendered templates (`slurp_ui`), reusing React CSS for chrome/layout. Legacy React app remains under `frontend/` and `/api/` still works.  
**How to open SLURP 2.0:** run Django (`backend_django\run-server.ps1`) and go to **http://127.0.0.1:8000/** (not Vite :5173).

**Status key**
- **Yes** — written in Python + Django templates with working core behavior equivalent enough for day-to-day use on that screen  
- **Partial** — Python templates + real data / navigation / header buttons present; major interactive sub-flows still missing vs React  
- **No** — shell/placeholder only (or stub form); workflow logic not ported  

---

## Summary

| Area | Yes | Partial | No |
|------|-----|---------|-----|
| Auth & shell | 7 | 1 | 0 |
| Inventory / **Buy + table** | **10** | 0 | 4+ |
| Sales / **Sell flow** | **10** | 2 | 0 |
| Finance / **Invoices** | **14** | 5 | 0 |
| Production / **Make flow** | **7** | 0 | 1 |
| Quality | **13** | 0 | 1+ |

**Bottom line:** Buy, Make, Sell, Invoice, CRM, Items CRUD, Activity Logs, Quality vendor/FG/R&D, and most Finance screens are **Yes** in Slurp 2. **E2E cutover complete** (backup + E2E/HTTP smoke rows removed from shared `wwi_erp.db`; plant masters kept). Calendar drag and some finance analytics remain Partial. Next session: tab redesign + finance overhaul.

---

## Buy flow milestone (done)

Shared services in `erp_core/buy_services.py` (also used by DRF API):

| Step | Status | Notes |
|------|--------|-------|
| Create Purchase Order | **Yes** | Vendor, ship-to, multi-line, discount/shipping, drop-ship flag, God-mode order date |
| Issue PO | **Yes** | Draft→issued, `on_order++`, PDF email best-effort; God-mode issue date |
| PO PDF | **Yes** | Inline / download via `po_pdf_html` |
| Revise / Cancel PO | **Yes** | Staff POST on PO list; shared `buy_services` |
| Check-In | **Yes** | Issued non–drop-ship POs; attestations + initials; vendor lot for RM; over-receipt block; lbs↔kg via `entry_uom`; AP on full receive |
| Reverse check-in | **Yes** | Calls `reverse_check_in_single_lot`; unused-lot eligibility list |

**E2E:** `scripts/e2e_buy_flow.py`

---

## Make flow milestone (done — production)

Shared services in `erp_core/make_services.py`:

| Step | Status | Notes |
|------|--------|-------|
| Create Batch Ticket (production) | **Yes** | Formula → lot/qty; lbs match; reserved until close |
| Close Batch | **Yes** | Wastes+spills explain shortfall; FG output `on_hold` |
| Reverse Batch | **Yes** | Restores inputs; blockers via `reversal_guard` |
| Repack UI | **Yes** | `batch_type=repack` on create; same-SKU lots; native UoM qty balance |
| Adjust batch | **Yes** | Wraps `adjust_batch_inputs`; open batches only |
| Batch detail + PDF | **Yes** | Detail page + `batch_ticket_pdf_html` download |

**E2E:** `scripts/e2e_make_flow.py`, `scripts/e2e_conversion_flow.py`

---

## Mass conversion (inventory)

Plant standard: **`LBS_PER_KG = 2.2`** in `erp_core/mass_quantity.py` and `frontend/src/utils/massQuantity.ts`.

---

## Sell flow milestone (done — core + reverse)

Shared services in `erp_core/sell_services.py`:

| Step | Status | Notes |
|------|--------|-------|
| Create Sales Order | **Yes** | Customer, ship-to, lines, drop-ship |
| Issue SO | **Yes** | Draft→issued; PDF email best-effort |
| Allocate | **Yes** | Lots per line; drop-ship virtual; prerepack override |
| Check Out (ship) | **Yes** | Carrier + pieces/dims/weights; draft invoice + AR |
| SO detail | **Yes** | Lines, shipments, invoices; actions |
| Reverse shipment | **Yes** | Staff; needs draft/cancelled invoice (`shipment_reversal`) |
| Revert to draft | **Yes** | Staff; blocked if shipments / shipped qty / issued invoices |
| Combined checkout | **Yes** | Multi-SO ship; shared carrier/pieces; combined packing list PDF |
| Pick / packing list PDF | **Yes** | SO list + detail links; combined key PDF after multi-ship |

**E2E:** `scripts/e2e_sell_flow.py`, `scripts/e2e_reverse_sell_flow.py`

---

## Invoice milestone (done)

| Step | Status | Notes |
|------|--------|-------|
| List | **Yes** | Status filter; Issue/PDF actions |
| Detail | **Yes** | Totals, lines, SO tracking; void / mark paid |
| Issue | **Yes** | Draft→sent; carrier/tracking required |
| PDF | **Yes** | Inline / download |
| Void | **Yes** | Mark cancelled |
| Manual create | **Yes** | Draft manual invoice + lines |
| Mark paid | **Yes** | Status-only (no A/R auto-close) |

**E2E:** `scripts/e2e_invoice_flow.py`

---

## Quality milestone (vendor + FG + tracking + COA + R&D)

| Step | Status | Notes |
|------|--------|-------|
| Vendor list + create | **Yes** | Status filter; Add vendor form |
| Vendor detail (all tabs) | **Yes** | Overview, contacts, survey, documents, items, exceptions, history |
| FG list + create + unlink | **Yes** | Formula on create; delete item (cascade formula) |
| FG formula editor | **Yes** | Version/QC/CCP/mixing/ingredients; Σ% ≈ 100 |
| Distributed item detail | **Yes** | Read-only (no formula); COA test lines link |
| Item COA test lines | **Yes** | Dedicated page per FG / distributed item |
| Lot tracking | **Yes** | Forward + backward |
| COA library | **Yes** | Master + customer tabs; PDF download |
| R&D formulas CRUD | **Yes** | List + edit BOM lines |
| Critical control points | **Yes** | Full CRUD |

**Remaining gaps (No):** Interactive supplier survey *submission*; FPS PDF; promote R&D to FG; exception reject workflow.

**E2E:** `scripts/e2e_quality_flow.py`

---

## 1. Auth

| Workflow | Status | Notes |
|----------|--------|-------|
| Sign in / forgot / reset / login required | **Yes** | |
| Staff sample XML import | **Yes** | Header button → `import-sample-xml/` (staff); loads `data/private_sample_data/` |
| Connection error banner | **No** | N/A same-origin |

## 2. Shell / header

| Workflow | Status | Notes |
|----------|--------|-------|
| Brand + module tabs + user/sign out | **Yes** | |
| God mode toggle | **Partial** | Session flag; not all date fields |
| Staff sample XML import | **Yes** | Same as React header |

## 3. Inventory

| Workflow | Status | Notes |
|----------|--------|-------|
| Inventory Table (SKU rollup) | **Yes** | Tabs FG/Raw/Indirect; expand; lot Hold / Release(+COA) / Reconcile |
| Items Management | **Yes** | List/search/filter; create (vendor, SKU, pack size); edit + ItemPackSize add/default/delete |
| Activity logs | **Yes** | All 6 React log types as tabbed read-only tables with filters |
| PO list / create / issue / PDF / revise / cancel / check-in / reverse | **Yes** | Buy flow |
| Indirect checkout | **Yes** | `lot_services.checkout_indirect_material` |

## 4. Sales

| Workflow | Status | Notes |
|----------|--------|-------|
| CRM dashboard | **Yes** | Search + active filter; location/contact/call counts |
| Manage Customers | **Yes** | Full create/edit/delete (blocked if SOs exist) |
| Customer profile + sub-entities | **Yes** | Overview, pricing, ship-to, contacts, sales calls, forecast, usage; linked create/edit/delete forms |
| SO list / create / allocate / issue / checkout / combined | **Yes** | |
| SO detail / reverse shipment / revert / pick & packing PDFs | **Yes** | |
| Single checkout (no SO selected) | **Partial** | List-only until an order is chosen |
| Sales Calendar | **Partial** | Month grid + event table + reschedule form (SO expected ship / batch production date); **no drag-and-drop** |

## 5. Finance

| Workflow | Status | Notes |
|----------|--------|-------|
| Dashboard | **Yes** | Invoice-first home (draft list + counts); not a metric clutter board |
| KPIs | **Yes** | On-time shipping KPI table |
| General Ledger — accounts list + create | **Yes** | |
| Journal Entries — list + create + post | **Yes** | |
| Fiscal Periods — list + create + close | **Yes** | Create form added |
| Bank Reconciliation | **Partial** | List + create; statement vs GL balance (no txn match UI) |
| Invoices list / detail / issue / PDF / void | **Yes** | |
| Manual create invoice / mark paid | **Yes** | |
| Accounts Receivable + payment entry | **Yes** | Open A/R list; record payment form |
| Accounts Payable + mark paid | **Partial** | A/P list + payment (no PO workqueue / add bill) |
| Pricing Management + vendor pricing | **Yes** | List + create customer/vendor pricing |
| Cost Master / margin trends / RM lot costs | **Partial** | Read lists + actuals / lot cost profile expand; no create/edit |
| Financial Reports / P&L Actual / Pro-Forma | **Yes** | Trial balance, balance sheet, income stmt, cash flow tables; pro-forma forecast edit |

## 6. Production

| Workflow | Status | Notes |
|----------|--------|-------|
| Batch list / create / close / reverse / repack / adjust / PDF | **Yes** | Production + repack paths |
| Reschedule (calendar UI) | **Partial** | Form on Sales Calendar; no drag-drop on production calendar |

## 7. Quality

| Workflow | Status | Notes |
|----------|--------|-------|
| Vendor Approval list + create | **Yes** | |
| Vendor detail (all tabs) | **Yes** | |
| Finished Goods list + create + unlink | **Yes** | |
| FG formula editor | **Yes** | |
| Distributed item detail | **Yes** | COA test lines; no formula editor |
| Item COA test lines | **Yes** | |
| Lot Tracking | **Yes** | |
| COA library | **Yes** | |
| R&D Formulas CRUD | **Yes** | |
| Critical Control Points | **Yes** | |
| Survey submission UI | **No** | Display only |
| FPS / promote R&D | **No** | |

---

## `port_status` checklist (view-level)

Screens still marked **`partial`** in view code:

| Module | Screen | Why still Partial |
|--------|--------|-------------------|
| Sales | `sales_calendar` | No drag-and-drop month UI |
| Sales | `sales_checkout` (no SO selected) | Order picker only |
| Finance | `finance_bank_recon` | No transaction matching |
| Finance | `finance_ap` | No PO workqueue / add bill |
| Finance | `finance_cost_master` | Read-only analytics |
| Finance | `finance_margin_trends` | Read-only analytics |
| Finance | `finance_rm_lot_costs` | Read-only analytics |

All other screens in `inventory.py`, `production.py`, `quality.py`, and the remaining `sales.py` / `finance.py` views are **`full`**.

---

## Recommended next ports

1. ~~Buy / Make / Sell / Invoice / CRM / Items / Logs / Quality~~ **Done**  
2. ~~Finance GL / journal / periods / AR / pricing / reports / manual invoice~~ **Done**  
3. Calendar drag-and-drop; bank recon txn match; AP PO workqueue; cost master create/edit  
4. Survey submit + FPS + R&D promote; ItemsList family rollup  
5. ~~E2E cutover (backup + purge test rows from shared SQLite)~~ **Done**  
6. Next session: tab redesign + finance overhaul; EC2 deploy when ready  

---

*Update this file as each workflow moves from No → Partial → Yes.*
