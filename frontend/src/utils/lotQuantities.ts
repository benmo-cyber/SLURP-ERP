/**
 * Net quantity free to allocate (sales allocation, hold, in-progress production).
 * Prefer API quantity_available_for_use — it matches backend compute_lot_quantity_breakdown.
 */
export type LotLikeForAvail = {
  quantity_available_for_use?: number | null
  quantity_remaining?: number | null
  quantity_on_hold?: number | null
  committed_to_production_qty?: number | null
}

export function lotAvailableForUse(lot: LotLikeForAvail): number {
  if (lot.quantity_available_for_use != null && !Number.isNaN(lot.quantity_available_for_use)) {
    return Math.max(0, lot.quantity_available_for_use)
  }
  const rem = lot.quantity_remaining ?? 0
  const hold = lot.quantity_on_hold ?? 0
  const prod = lot.committed_to_production_qty ?? 0
  return Math.max(0, rem - hold - prod)
}
