import { api } from './client'

export const getCostMasters = async (opts?: { commercialRaw?: boolean }) => {
  const params: Record<string, string> = {}
  if (opts?.commercialRaw) params.commercial_raw = 'true'
  const response = await api.get('/cost-master/', { params })
  return response.data.results || response.data
}

/** Per-lot actual vs estimate for a Cost Master (commercial raw material profile). */
export const getLotCostProfile = async (costMasterId: number) => {
  const response = await api.get(`/cost-master/${costMasterId}/lot_cost_profile/`)
  return response.data as LotCostProfileResponse
}

export interface LotCostProfileRow {
  lot_id: number
  lot_number: string | null
  po_number: string | null
  received_date: string | null
  quantity_received: number
  quantity_remaining: number
  item_sku: string
  item_uom: string
  po_unit_price: number | null
  po_price_uom: string | null
  price_per_kg_from_po: number | null
  shipment_freight_per_kg: number | null
  shipment_tariff_rate: number | null
  /** Allocated from AP (material category) + PO lines, scaled to invoice total */
  allocated_material_usd?: number | null
  allocated_freight_usd?: number | null
  allocated_duty_usd?: number | null
  lot_freight_actual_usd?: number | null
  cert_cost_usd?: number | null
  total_actual_cost_usd?: number | null
  actual_landed_per_kg: number | null
  actual_landed_per_lb: number | null
  /** total_actual_cost_usd / quantity_received in native UOM */
  actual_landed_per_uom?: number | null
  estimate_landed_per_kg: number | null
  variance_per_kg: number | null
  comparison: 'over' | 'under' | 'ok'
  ap_invoice_number: string | null
  has_po_match: boolean
  has_ap_allocation: boolean
  has_cost_components?: boolean
}

export interface LotCostProfileResponse {
  cost_master_id: number
  vendor_material?: string
  wwi_product_code: string | null
  vendor: string | null
  estimate_landed_per_kg?: number | null
  estimate_landed_per_lb?: number | null
  lots: LotCostProfileRow[]
  raw_material_item_ids?: number[]
  message?: string
  methodology?: string
}

export const getCostMaster = async (id: number) => {
  const response = await api.get(`/cost-master/${id}/`)
  return response.data
}

export const createCostMaster = async (data: any) => {
  const response = await api.post('/cost-master/', data)
  return response.data
}

export const updateCostMaster = async (id: number, data: any) => {
  const response = await api.put(`/cost-master/${id}/`, data)
  return response.data
}

export const deleteCostMaster = async (id: number) => {
  const response = await api.delete(`/cost-master/${id}/`)
  return response.data
}

export const getCostMasterByProductCode = async (productCode: string, vendor?: string) => {
  let url = `/cost-master/?product_code=${productCode}`
  if (vendor) {
    url += `&vendor=${encodeURIComponent(vendor)}`
  }
  const response = await api.get(url)
  const data = response.data.results || response.data
  return Array.isArray(data) && data.length > 0 ? data[0] : null
}

export const getPricingHistory = async (productCodes: string[]) => {
  const params = productCodes.map(code => `product_code=${code}`).join('&')
  const response = await api.get(`/cost-master/pricing_history/?${params}`)
  return response.data
}

export const getCostMasterHistory = async (costMasterId: number) => {
  const response = await api.get(`/cost-master/${costMasterId}/history/`)
  return response.data
}


export const refreshTariffs = async () => {
  const response = await api.post('/cost-master/refresh_tariffs/')
  return response.data
}

/** Actual cost metrics from AP (avg tariff %, avg freight/UoM, comparison to estimate). Keyed by cost_master id. */
export const getCostMasterActuals = async (ids?: number[]) => {
  const params = ids?.length ? { id: ids } : {}
  const response = await api.get('/cost-master/actuals/', { params })
  return response.data as Record<number, {
    avg_tariff_pct?: number
    avg_freight_per_kg?: number
    actual_landed_per_kg?: number
    estimated_landed_per_kg?: number | null
    comparison: 'over' | 'under' | 'ok'
    shipments_count: number
  }>
}
