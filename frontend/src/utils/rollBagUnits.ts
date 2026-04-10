/**
 * Inventory for many items is in "rolls" (item UOM = ea) while pack master data
 * describes bags per roll (e.g. 175 pcs per roll). POs stay in rolls; production
 * can allocate in individual bags by converting bags ↔ rolls here.
 */

export interface PackSizeLike {
  pack_size: number
  pack_size_unit: string
}

/** Bags per one inventory ea (roll), from ItemPackSize on the lot. */
export function getBagsPerRollFromPackSize(pack: PackSizeLike | null | undefined): number | null {
  if (!pack || pack.pack_size == null || pack.pack_size <= 0) return null
  let u = (pack.pack_size_unit || '').trim().toLowerCase()
  if (!u) u = 'pcs'
  // 175 pcs = 175 bags per roll; some masters use ea for "units per roll"
  if (u === 'pcs' || u === 'pc' || u === 'ea' || u === 'piece' || u === 'pieces') return pack.pack_size
  return null
}

export function getBagsPerInventoryEa(lot: {
  item: { unit_of_measure: string }
  pack_size_obj?: PackSizeLike | null
}): number | null {
  if (lot.item.unit_of_measure !== 'ea') return null
  return getBagsPerRollFromPackSize(lot.pack_size_obj ?? undefined)
}

/** Lot API may omit pack_size_obj; use item default_pack_size / pack_sizes (pcs/ea = bags per roll). */
export function resolveBagsPerRollForLot(lot: {
  pack_size_obj?: PackSizeLike | null
  item?: {
    unit_of_measure?: string
    pack_sizes?: PackSizeLike[]
    default_pack_size?: PackSizeLike | null
  }
}): number | null {
  const uom = (lot.item?.unit_of_measure || '').trim().toLowerCase()
  if (uom !== 'ea') return null
  const fromLot = getBagsPerRollFromPackSize(lot.pack_size_obj ?? undefined)
  if (fromLot != null) return fromLot
  const def = lot.item?.default_pack_size
  if (def) {
    const b = getBagsPerRollFromPackSize(def)
    if (b != null) return b
  }
  for (const ps of lot.item?.pack_sizes ?? []) {
    const b = getBagsPerRollFromPackSize(ps)
    if (b != null) return b
  }
  return null
}

/** API may send bags_per_roll as string; JSON sometimes stringifies numbers. */
export function coercePositiveBagsPerRoll(value: unknown): number | null {
  if (value == null || value === '') return null
  const n = typeof value === 'number' ? value : parseFloat(String(value).replace(/,/g, ''))
  if (!Number.isFinite(n) || n <= 0) return null
  return n
}

export function bagsToRolls(bags: number, bagsPerRoll: number): number {
  if (bagsPerRoll <= 0) return 0
  return Math.round((bags / bagsPerRoll) * 1e6) / 1e6
}

export function rollsToBags(rolls: number, bagsPerRoll: number): number {
  return Math.round(rolls * bagsPerRoll * 1000) / 1000
}
