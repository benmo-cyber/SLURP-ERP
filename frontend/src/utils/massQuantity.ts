import { formatNumber, formatNumberFlexible } from './formatNumber'

/** Plant standard: 2.2 lb = 1 kg (must match backend erp_core.mass_quantity.LBS_PER_KG). */
export const LBS_PER_KG = 2.2

/** Same tolerance as backend erp_core.mass_quantity */
const MASS_INT_SNAP_TOLERANCE = 0.01

/** Sums / rollups (matches backend AGGREGATE_MASS_SNAP_TOLERANCE) */
const AGGREGATE_MASS_SNAP_TOLERANCE = 0.05

export function normalizeAggregateMassQuantity(value: number): number {
  if (!Number.isFinite(value)) return value
  const v = Math.round(value * 100) / 100
  const n = Math.round(v)
  if (Math.abs(v - n) <= AGGREGATE_MASS_SNAP_TOLERANCE + 1e-9) {
    return n
  }
  return v
}

/**
 * Round to 2 decimal places, then snap to the nearest whole number when within 0.01
 * (fixes 699.99 → 700, 3149.96 → 3150 from float drift / kg↔lbs conversion).
 */
export function normalizeMassQuantity(value: number): number {
  if (!Number.isFinite(value)) return value
  const v = Math.round(value * 100) / 100
  const n = Math.round(v)
  // +1e-9: IEEE so abs(99.99-100) is slightly > 0.01 without epsilon
  if (Math.abs(v - n) <= MASS_INT_SNAP_TOLERANCE + 1e-9) {
    return n
  }
  return v
}

export function convertMassUom(
  quantity: number,
  fromUnit: string,
  toUnit: string
): number {
  const src = (fromUnit || '').toLowerCase() === 'lb' ? 'lbs' : (fromUnit || '').toLowerCase()
  const dst = (toUnit || '').toLowerCase() === 'lb' ? 'lbs' : (toUnit || '').toLowerCase()
  if (!Number.isFinite(quantity) || src === dst) return normalizeMassQuantity(quantity)
  if (src === 'lbs' && dst === 'kg') return normalizeMassQuantity(quantity / LBS_PER_KG)
  if (src === 'kg' && dst === 'lbs') return normalizeMassQuantity(quantity * LBS_PER_KG)
  return quantity
}

/** ea / rolls: integer snap or 5 dp (aligns with backend batch input rounding). */
export function normalizeEaQuantity(value: number): number {
  if (!Number.isFinite(value)) return value
  const ri = Math.round(value)
  if (Math.abs(value - ri) <= MASS_INT_SNAP_TOLERANCE) {
    return ri
  }
  return Math.round(value * 1e5) / 1e5
}

/** After normalization, format for display (commas + decimals). */
export function formatMassQuantity(value: number | null | undefined, decimals: number = 2): string {
  if (value == null || !Number.isFinite(value)) return ''
  return formatNumber(normalizeMassQuantity(value), decimals)
}

/**
 * Single entry point for inventory table: convert stored qty to display unit, then normalize + format.
 * Uses plant standard LBS_PER_KG (2.2).
 */
export function formatQuantityForDisplay(
  quantity: number,
  storageUnit: string,
  displayUnit: 'lbs' | 'kg'
): string {
  const u = (storageUnit || '').toLowerCase()
  if (u === 'ea') {
    return formatNumber(normalizeEaQuantity(quantity), 0)
  }

  let displayValue = quantity
  if (displayUnit === 'kg' && (u === 'lbs' || u === 'lb')) {
    displayValue = convertMassUom(quantity, 'lbs', 'kg')
  } else if (displayUnit === 'lbs' && u === 'kg') {
    displayValue = convertMassUom(quantity, 'kg', 'lbs')
  }

  const rounded2 = Math.round(displayValue * 100) / 100
  const normalized = normalizeAggregateMassQuantity(rounded2)
  const asInt = Math.round(normalized)
  if (Math.abs(normalized - asInt) <= AGGREGATE_MASS_SNAP_TOLERANCE) {
    return formatNumberFlexible(asInt, 0, 0)
  }
  return formatNumber(normalized, 2)
}
