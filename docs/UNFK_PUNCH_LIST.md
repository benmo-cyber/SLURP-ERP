# UNFK punch list & user-manual notes

This document is a **working punch list** for reversal / “UNFK” behavior across the app, plus **authoritative answers** (from current code) for confusing areas—especially **finished goods (FG)** vs **receipt reversal** vs **batch tickets**. Update it as features ship.

---

## 1. Terminology (UI uses explicit verbs)

Older builds used the slang label **UNFK** in several places; the UI now prefers **Reverse check-in**, **Reverse batch**, **Delete item**, and **Unlink finished good** so operators are not misled. Backend ledger notes may still contain legacy “UNFK” text on some transactions.

| Surface | What it actually does | Reverses batch / repack? | Reverses PO check-in? |
|--------|------------------------|---------------------------|------------------------|
| **Quality → Finished Goods → “Unlink finished good”** | Deletes the **Item** master record (`DELETE /api/items/{id}/`). Warns about formula/FPS. | **No.** | **No.** |
| **Inventory → Items list → “Delete item”** (per row) | Same: **delete Item** via `deleteItem`. | **No.** | **No.** |
| **Purchasing → PO list / PO detail → “Reverse check-in”** | **Reverse check-in** for a **Lot** (`reverseCheckIn` / `bulkReverseCheckIn`): removes the receipt lot and rolls back PO received qty when possible. | **No.** | **Yes** (for that receipt lot). |
| **Inventory → “Reverse check-in”** (header admin modal) | Same backend on a selected lot. | **No.** | **Yes** (that lot). |
| **Production → “Reverse batch”** | `POST /api/production-batches/{id}/reverse/` — reverses that batch (restore inputs if closed, delete output lots, delete batch). Ledger notes may still say UNFK internally. | **Yes** (that batch only). | **No.** |

**Inventory lot grid (SKU × vendor table):** There is no receipt-reversal button on the main lot rows; use **PO → Reverse check-in** or **Inventory → Reverse check-in**.

---

## 2. Answers for the manual: FG, repack, production, and check-in

### Q: If a FG is “UNFK’d” from the Finished Goods / Items screen, does that reverse the repack or batch ticket?

**A:** **No.** That action deletes the **finished good Item** record (after optionally snapshotting orphaned inventory / PO lines in the backend). It does **not** walk backward through production batches, repacks, or output lots. If you need to undo a batch, use **batch reverse** (`production-batches/.../reverse/`), not Item UNFK.

### Q: Does FG UNFK only reverse the check-in process?

**A:** **No.** Check-in reversal is a **Lot** operation (`reverse_check_in` / `reverseCheckIn`). FG UNFK is **Item deletion**, not check-in reversal.

### Q: What if someone tries to UNFK a FG that was produced or repacked (output lot exists)?

**A:** Item delete may still proceed with **orphan snapshots** for remaining quantity and cascade deletes; **do not assume** it cleanly “unwraps” production. Operators should treat **Unlink finished good** as **removing the SKU row from the catalog**, not as undoing manufacturing. Prefer **batch reverse** first if the goal is to undo a mistaken batch.

### Q: Does reverse check-in undo production *and* un-check-in raw material?

**A:** **No.** Reverse check-in operates on **one lot** (typically a **receipt** lot). The API **refuses** if:

- The lot has **sales order allocations** (`SalesOrderLot`), or  
- The lot appears as **input** to a **production batch** (`ProductionBatchInput`).

See `reverse_check_in_single_lot` in `erp_core/views.py` (errors: *Cannot reverse check-in: lot is allocated…* / *…used in production batches…*).

So: **you cannot** reverse a raw material check-in that was already consumed in production without first reversing that production usage (today: manual / batch reverse—no single combined button).

### Q: What does batch “reverse” do vs. receipt UNFK?

**A:** **Batch reverse** tries to undo **one production/repack batch** (restore closed-batch inputs, delete output lots, delete batch, etc.). **Receipt UNFK** only undoes **receiving** that lot onto a PO. They are different layers of the stack.

---

## 3. Punch list — gaps to build (reversal / UNFK roadmap)

### 3.1 Completed sales orders

- [ ] **Define product behavior:** “Undo completion” vs “full reversal to issued + unallocated” vs “reverse shipment only.”
- [ ] **Backend:** Orchestrate in dependency order (e.g. shipment / invoice / inventory implications before clearing allocations). See existing `reverse_shipment` in `erp_core/shipment_reversal.py` as a primitive.
- [ ] **UI:** Staff-only action, preconditions, dry-run or clear error messages.
- [ ] **Docs:** User manual section on what is reversible after ship and what requires accounting.

### 3.2 Sales order allocations — **un-allocate** (distinct from re-allocate)

- [ ] **Clarify:** “Un-allocate” = remove all `SalesOrderLot` rows and clear line `quantity_allocated` without necessarily opening the full allocate modal (re-allocate already replaces allocation interactively).
- [ ] **Backend:** New action or documented use of existing allocate/cancel paths; ensure **customer COA** (`LotCoaCustomerCopy`) lifecycle matches business rules when allocations are removed.
- [ ] **UI:** Explicit **Un-allocate** button with confirmation when status allows it.
- [ ] **Docs:** When to use un-allocate vs cancel SO vs reverse shipment.

### 3.3 Inventory table / UX clarity

- [ ] **Rename or tooltips:** Consider replacing generic **UNFK** on Item rows with **“Delete item (unlink)”** or similar to avoid confusion with **PO receipt UNFK**.
- [ ] **Optional:** If lot-level receipt reversal should live next to lots on the inventory grid, add a **Reverse check-in** action with the same rules as the API (and link to PO context).

### 3.4 Unified “reversal matrix” (for manual + dev)

- [ ] Table: **Entity** × **Reversal available?** × **API / UI** × **Blockers** (e.g. allocated lot, posted invoice).

### 3.5 User manual (separate doc)

- [ ] Extract sections from this file once behavior stabilizes.
- [ ] Add screenshots for: PO UNFK modal, FG Unlink, batch reverse (if exposed in UI), allocate vs un-allocate.

---

## 4. Code references (for maintainers)

| Topic | Location |
|-------|----------|
| Reverse check-in rules & errors | `erp_core/views.py` — `reverse_check_in_single_lot`, `LotViewSet.reverse_check_in`, `bulk_reverse_check_in` |
| Item delete (FG / Items UNFK) | `ItemViewSet.destroy` in `erp_core/views.py` |
| Batch reverse | `ProductionBatchViewSet.reverse` in `erp_core/views.py` |
| Shipment reverse | `erp_core/shipment_reversal.py` — `reverse_shipment` |
| PO status after receipt rollback | `reconcile_purchase_order_status_from_lines` in `erp_core/views.py` |

---

*Last reviewed: aligned with frontend Items / Finished Goods / PO UNFK and backend reverse-check-in + batch reverse as of doc creation.*
