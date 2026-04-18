import { api } from './client'

// Items API
export const getItems = async (
  approvedVendorsOrOptions?: boolean | {
    approvedVendorsOnly?: boolean
    skuMastersOnly?: boolean
  }
) => {
  let approvedVendorsOnly = false
  let skuMastersOnly = false
  if (typeof approvedVendorsOrOptions === 'boolean') {
    approvedVendorsOnly = approvedVendorsOrOptions
  } else if (approvedVendorsOrOptions && typeof approvedVendorsOrOptions === 'object') {
    approvedVendorsOnly = !!approvedVendorsOrOptions.approvedVendorsOnly
    skuMastersOnly = !!approvedVendorsOrOptions.skuMastersOnly
  }
  const params = new URLSearchParams()
  if (approvedVendorsOnly) params.set('approved_vendors_only', 'true')
  if (skuMastersOnly) params.set('sku_masters_only', 'true')
  const q = params.toString()
  const url = q ? `/items/?${q}` : '/items/'
  const response = await api.get(url)
  return response.data.results || response.data
}

export const getItem = async (id: number) => {
  const response = await api.get(`/items/${id}/`)
  return response.data
}

export const createItem = async (data: any) => {
  const response = await api.post('/items/', data)
  return response.data
}

export const updateItem = async (id: number, data: any) => {
  const response = await api.patch(`/items/${id}/`, data)
  return response.data
}

export const deleteItem = async (id: number) => {
  const response = await api.delete(`/items/${id}/`)
  return response.data
}

// Item Pack Sizes API
export const getItemPackSizes = async (itemId?: number) => {
  const url = itemId ? `/item-pack-sizes/?item_id=${itemId}` : '/item-pack-sizes/'
  const response = await api.get(url)
  return response.data.results || response.data
}

export const createItemPackSize = async (data: any) => {
  const response = await api.post('/item-pack-sizes/', data)
  return response.data
}

export const updateItemPackSize = async (id: number, data: any) => {
  const response = await api.put(`/item-pack-sizes/${id}/`, data)
  return response.data
}

export const deleteItemPackSize = async (id: number) => {
  const response = await api.delete(`/item-pack-sizes/${id}/`)
  return response.data
}

// Lots API
export const getLots = async () => {
  const response = await api.get('/lots/')
  // Handle paginated response
  return response.data.results || response.data
}

export const createLot = async (data: any) => {
  // The backend expects lot_number to be generated, so we'll send the data
  // and let the backend handle lot number generation
  const payload: any = {
    item_id: data.item_id,
    quantity: parseFloat(data.quantity) || 0, // Ensure quantity is a number
    received_date: data.received_date,
    status: data.status || 'accepted',
  }
  
  if (data.expiration_date != null && String(data.expiration_date).trim() !== '') {
    payload.expiration_date = data.expiration_date
  }
  if (data.freight_actual) payload.freight_actual = parseFloat(data.freight_actual) || null
  if (data.po_number) payload.po_number = data.po_number
  if (data.lot_number && data.lot_number.trim()) payload.lot_number = data.lot_number.trim() // Manual/legacy lot number
  if (data.vendor_lot_number) payload.vendor_lot_number = data.vendor_lot_number
  if (data.short_reason && data.short_reason.trim()) payload.short_reason = data.short_reason.trim()
  // Add check-in form fields
  if (data.coa !== undefined) payload.coa = data.coa
  if (data.prod_free_pests !== undefined) payload.prod_free_pests = data.prod_free_pests
  if (data.carrier_free_pests !== undefined) payload.carrier_free_pests = data.carrier_free_pests
  if (data.shipment_accepted !== undefined) payload.shipment_accepted = data.shipment_accepted
  if (data.initials) payload.initials = data.initials
  // Always send carrier so the check-in log row stores it (backend also falls back to PO carrier if blank)
  if (data.carrier !== undefined && data.carrier !== null) {
    payload.carrier = String(data.carrier).trim()
  }
  if (data.notes) payload.notes = data.notes
  
  console.log('API payload:', payload)
  const response = await api.post('/lots/', payload)
  return response.data
}

export const reverseCheckIn = async (lotId: number) => {
  const response = await api.post(`/lots/${lotId}/reverse-check-in/`)
  return response.data
}

export type BulkReverseCheckInResult = {
  reversed: { lot_number?: string; item_sku?: string; quantity?: number }[]
  failed: { lot_id?: number; lot_number?: string; error: string }[]
  message?: string
}

/** Reverse many receipt lots. Send lotIds and/or poNumber (union: po adds every lot on that PO). */
export const bulkReverseCheckIn = async (params: {
  lotIds?: number[]
  poNumber?: string
}): Promise<BulkReverseCheckInResult> => {
  const body: Record<string, unknown> = {}
  if (params.lotIds?.length) body.lot_ids = params.lotIds
  if (params.poNumber?.trim()) body.po_number = params.poNumber.trim()
  const response = await api.post('/lots/bulk-reverse-check-in/', body)
  return response.data
}

/** Lots with this PO number (check-in / receipt history on PO detail). */
export const getLotsByPurchaseOrder = async (poNumber: string) => {
  const response = await api.get('/lots/by-po/', { params: { po_number: poNumber } })
  return response.data
}

export const updateLot = async (lotId: number, data: any) => {
  const response = await api.patch(`/lots/${lotId}/`, data)
  return response.data
}

/** Regenerate stored master + customer COA PDFs from current lot data (e.g. after template edits). */
export const regenerateLotCoa = async (lotId: number) => {
  const response = await api.post(`/lots/${lotId}/regenerate-coa/`)
  return response.data
}

export const putLotOnHold = async (lotId: number, quantity: number) => {
  const response = await api.post(`/lots/${lotId}/put_on_hold/`, { quantity })
  return response.data
}

export type ReleaseFromHoldCoaPayload = {
  qc_result_value?: number
  line_results: { item_line_id: number; result_text: string }[]
}

export const releaseLotFromHold = async (
  lotId: number,
  quantity: number,
  coa?: ReleaseFromHoldCoaPayload
) => {
  const body: Record<string, unknown> = { quantity }
  if (coa) body.coa = coa
  const response = await api.post(`/lots/${lotId}/release_from_hold/`, body)
  return response.data
}

/** Admin: set on-hand only (quantity_remaining). Does not change received (quantity). Requires staff. */
export const reconcileLot = async (lotId: number, quantityRemaining: number, reason: string) => {
  const response = await api.post(`/lots/${lotId}/reconcile/`, { quantity_remaining: quantityRemaining, reason: reason || 'Admin reconcile' })
  return response.data
}

/** Admin: set received total only (lot.quantity). Does not change on-hand (quantity_remaining). Requires staff. */
export const adjustLotReceived = async (lotId: number, quantity: number, reason: string) => {
  const response = await api.post(`/lots/${lotId}/adjust_received/`, {
    quantity,
    reason: reason || 'Adjust received quantity',
  })
  return response.data
}

// Campaign lots (YYWW + product code; ISO week from anchor_date)
export type CampaignLot = {
  id: number
  item: number
  anchor_date: string
  product_code: string
  campaign_code: string
  iso_year: number
  iso_week: number
  notes?: string
}

export const getCampaignLots = async (itemId: number) => {
  const response = await api.get(`/campaign-lots/?item=${itemId}`)
  return (response.data.results || response.data) as CampaignLot[]
}

export const createCampaignLot = async (data: {
  item: number
  anchor_date: string
  product_code: string
  notes?: string
}) => {
  const response = await api.post('/campaign-lots/', data)
  return response.data as CampaignLot
}

// Production Batches API
export const getProductionBatches = async () => {
  const response = await api.get('/production-batches/')
  // Handle paginated response
  return response.data.results || response.data
}

export const getProductionBatch = async (id: number) => {
  const response = await api.get(`/production-batches/${id}/`)
  return response.data
}

export const updateProductionBatch = async (id: number, data: any) => {
  const response = await api.patch(`/production-batches/${id}/`, data)
  return response.data
}

export const createProductionBatch = async (data: any) => {
  const response = await api.post('/production-batches/', data)
  return response.data
}

export const reverseBatchTicket = async (batchId: number) => {
  const response = await api.post(`/production-batches/${batchId}/reverse/`)
  return response.data
}

/** Blockers + suggested_steps before reversing a batch (GET). */
export const getProductionBatchReversalPlan = async (batchId: number) => {
  const response = await api.get(`/production-batches/${batchId}/reversal-plan/`)
  return response.data
}

/** Undo one SO shipment (inventory, draft invoice, allocations); use before reversing a batch whose lot shipped. */
export const reverseShipment = async (shipmentId: number) => {
  const response = await api.post(`/shipments/${shipmentId}/reverse/`)
  return response.data
}

export const getPartialLots = async (finishedGoodItemId: number) => {
  const response = await api.get(`/production-batches/partials/?finished_good_item_id=${finishedGoodItemId}`)
  return response.data
}

// Critical Control Points (CCP) API – for batch ticket pre-production checks
export const getCriticalControlPoints = async () => {
  const response = await api.get('/critical-control-points/')
  return response.data.results || response.data
}

export const createCriticalControlPoint = async (data: { name: string; display_order?: number }) => {
  const response = await api.post('/critical-control-points/', data)
  return response.data
}

export const updateCriticalControlPoint = async (id: number, data: { name?: string; display_order?: number }) => {
  const response = await api.put(`/critical-control-points/${id}/`, data)
  return response.data
}

export const deleteCriticalControlPoint = async (id: number) => {
  await api.delete(`/critical-control-points/${id}/`)
}

// Formulas API
export const getFormulas = async () => {
  const response = await api.get('/formulas/')
  // Handle paginated response
  return response.data.results || response.data
}

export const getFormula = async (id: number) => {
  const response = await api.get(`/formulas/${id}/`)
  return response.data
}

export const createFormula = async (data: any) => {
  const response = await api.post('/formulas/', data)
  return response.data
}

export const updateFormula = async (id: number, data: any) => {
  const response = await api.put(`/formulas/${id}/`, data)
  return response.data
}

// Purchase Orders API
export const getPurchaseOrders = async () => {
  const response = await api.get('/purchase-orders/')
  // Handle paginated response
  return response.data.results || response.data
}

export const createPurchaseOrder = async (data: any) => {
  const response = await api.post('/purchase-orders/', data)
  return response.data
}

// Sales Orders API
export const getSalesOrders = async () => {
  const response = await api.get('/sales-orders/')
  // Handle paginated response
  return response.data.results || response.data
}

export const createSalesOrder = async (data: any) => {
  const response = await api.post('/sales-orders/', data)
  return response.data
}

// Inventory Details API
// inventoryTable: 'finished_good' | 'raw_material' | 'indirect_material' for split tables (distributed: raw until repack closed, then FG)
export const getInventoryDetails = async (inventoryTable?: string) => {
  const params = new URLSearchParams()
  if (inventoryTable) {
    params.append('inventory_table', inventoryTable)
  }
  const url = params.toString() ? `/lots/inventory_details/?${params}` : '/lots/inventory_details/'
  const response = await api.get(url)
  return response.data
}

// Get lots by SKU and vendor
export const getLotsBySkuVendor = async (
  sku: string,
  vendor?: string,
  inventoryTable?: 'finished_good' | 'raw_material' | 'indirect_material',
  options?: { deeper?: boolean }
) => {
  const params = new URLSearchParams({ sku })
  if (vendor) {
    params.append('vendor', vendor)
  }
  if (inventoryTable) {
    params.append('inventory_table', inventoryTable)
  }
  if (options?.deeper) {
    params.append('deeper', '1')
  }
  try {
    const response = await api.get(`/lots/lots_by_sku_vendor/?${params}`)
    // If response contains an error, return empty array
    if (response.data && typeof response.data === 'object' && !Array.isArray(response.data) && response.data.error) {
      console.warn(`API returned error for SKU ${sku}, vendor ${vendor}:`, response.data.error)
      return []
    }
    return response.data || []
  } catch (error: any) {
    // Handle 404 and other errors
    if (error.response?.status === 404) {
      console.warn(`No items found for SKU ${sku}, vendor ${vendor}`)
      return []
    }
    console.error(`Error fetching lots for SKU ${sku}, vendor ${vendor}:`, error)
    throw error
  }
}

/** Lots for a single Item row (matches inventory rules for the given inventory_table tab). */
export const getLotsByItemId = async (
  itemId: number,
  inventoryTable?: 'finished_good' | 'raw_material' | 'indirect_material',
  options?: { deeper?: boolean }
) => {
  const params = new URLSearchParams({ item_id: String(itemId) })
  if (inventoryTable) {
    params.append('inventory_table', inventoryTable)
  }
  if (options?.deeper) {
    params.append('deeper', '1')
  }
  try {
    const response = await api.get(`/lots/lots_by_sku_vendor/?${params}`)
    if (response.data && typeof response.data === 'object' && !Array.isArray(response.data) && response.data.error) {
      console.warn(`API returned error for item ${itemId}:`, response.data.error)
      return []
    }
    return response.data || []
  } catch (error: any) {
    if (error.response?.status === 404) {
      return []
    }
    console.error(`Error fetching lots for item ${itemId}:`, error)
    throw error
  }
}

// Lot Depletion Logs API
export interface LotDepletionLog {
  id: number
  lot: number
  lot_number: string
  item_sku: string
  item_name: string
  vendor?: string
  initial_quantity: number
  quantity_before: number
  quantity_used: number
  final_quantity: number
  depletion_method: 'production' | 'sales' | 'adjustment' | 'manual' | 'reversal'
  depletion_method_display: string
  reference_number?: string
  reference_type?: string
  transaction_id?: number
  batch_id?: number
  sales_order_id?: number
  notes?: string
  depleted_at: string
}

export const getLotDepletionLogs = async (filters?: {
  lot_number?: string
  sku?: string
  method?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.lot_number) params.append('lot_number', filters.lot_number)
  if (filters?.sku) params.append('sku', filters.sku)
  if (filters?.method) params.append('method', filters.method)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  
  const url = params.toString() ? `/lot-depletion-logs/?${params}` : '/lot-depletion-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}

// Lot Transaction Logs API
export interface LotTransactionLog {
  id: number
  lot: number
  lot_number: string
  item_sku: string
  item_name: string
  vendor?: string
  transaction_type: 'receipt' | 'production_input' | 'production_output' | 'repack_input' | 'repack_output' | 'sale' | 'adjustment' | 'allocation' | 'deallocation' | 'manual' | 'reversal'
  transaction_type_display: string
  quantity_before: number
  quantity_change: number
  quantity_after: number
  reference_number?: string
  reference_type?: string
  transaction_id?: number
  batch_id?: number
  sales_order_id?: number
  purchase_order_id?: number
  notes?: string
  logged_at: string
  logged_by?: string
}

export const getLotTransactionLogs = async (filters?: {
  lot_number?: string
  sku?: string
  transaction_type?: string
  reference_number?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.lot_number) params.append('lot_number', filters.lot_number)
  if (filters?.sku) params.append('sku', filters.sku)
  if (filters?.transaction_type) params.append('transaction_type', filters.transaction_type)
  if (filters?.reference_number) params.append('reference_number', filters.reference_number)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  
  const url = params.toString() ? `/lot-transaction-logs/?${params}` : '/lot-transaction-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}

// Purchase Order Logs API
export interface PurchaseOrderLog {
  id: number
  purchase_order: number
  po_number: string
  action: 'created' | 'updated' | 'check_in' | 'partial_check_in' | 'cancelled' | 'completed'
  action_display: string
  vendor_name?: string
  vendor_customer_name?: string
  po_date?: string
  required_date?: string
  status?: string
  carrier?: string
  lot_number?: string
  item_sku?: string
  item_name?: string
  quantity_received?: number
  received_date?: string
  po_received_date?: string
  total_items: number
  total_quantity_ordered: number
  total_quantity_received: number
  notes?: string
  logged_at: string
  logged_by?: string
}

export const getPurchaseOrderLogs = async (filters?: {
  po_number?: string
  vendor?: string
  action?: string
  lot_number?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.po_number) params.append('po_number', filters.po_number)
  if (filters?.vendor) params.append('vendor', filters.vendor)
  if (filters?.action) params.append('action', filters.action)
  if (filters?.lot_number) params.append('lot_number', filters.lot_number)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  
  const url = params.toString() ? `/purchase-order-logs/?${params}` : '/purchase-order-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}

// Production Logs API
export interface ProductionLog {
  id: number
  batch: number
  batch_number: string
  batch_type: 'production' | 'repack'
  finished_good_sku: string
  finished_good_name: string
  quantity_produced: number
  quantity_actual: number
  variance: number
  wastes: number
  spills: number
  production_date: string
  closed_date: string
  input_materials?: string
  input_lots?: string
  output_lot_number?: string
  output_quantity?: number
  qc_parameters?: string
  qc_actual?: string
  qc_initials?: string
  notes?: string
  closed_by?: string
  logged_at: string
}

export const getProductionLogs = async (filters?: {
  batch_number?: string
  sku?: string
  batch_type?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.batch_number) params.append('batch_number', filters.batch_number)
  if (filters?.sku) params.append('sku', filters.sku)
  if (filters?.batch_type) params.append('batch_type', filters.batch_type)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  
  const url = params.toString() ? `/production-logs/?${params}` : '/production-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}

// Check-In Logs API
export interface CheckInLog {
  id: number
  lot?: number
  lot_number: string
  item_id?: number
  item_sku: string
  item_name: string
  item_type: string
  item_unit_of_measure: 'lbs' | 'kg' | 'ea'
  po_number?: string
  vendor_name?: string
  received_date: string
  manufacture_date?: string | null
  expiration_date?: string | null
  vendor_lot_number?: string
  quantity: number
  quantity_unit: 'lbs' | 'kg' | 'ea'
  status: 'accepted' | 'rejected' | 'on_hold'
  short_reason?: string
  coa: boolean
  prod_free_pests: boolean
  carrier_free_pests: boolean
  shipment_accepted: boolean
  initials?: string
  carrier?: string
  freight_actual?: number
  notes?: string
  checked_in_at: string
  checked_in_by?: string
}

export const getCheckInLogs = async (filters?: {
  item_sku?: string
  po_number?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.item_sku) params.append('item_sku', filters.item_sku)
  if (filters?.po_number) params.append('po_number', filters.po_number)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  
  const url = params.toString() ? `/check-in-logs/?${params}` : '/check-in-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}

// Lot attribute change logs (e.g. expiration date corrections after re-QC)
export interface LotAttributeChangeLog {
  id: number
  lot: number
  lot_number?: string
  item_sku?: string
  field_name: string
  old_value: string
  new_value: string
  reason: string
  changed_at: string
  changed_by: string
}

export const getLotAttributeChangeLogs = async (filters?: {
  lot_number?: string
  sku?: string
  field_name?: string
  date_from?: string
  date_to?: string
}) => {
  const params = new URLSearchParams()
  if (filters?.lot_number) params.append('lot_number', filters.lot_number)
  if (filters?.sku) params.append('sku', filters.sku)
  if (filters?.field_name) params.append('field_name', filters.field_name)
  if (filters?.date_from) params.append('date_from', filters.date_from)
  if (filters?.date_to) params.append('date_to', filters.date_to)
  const url = params.toString() ? `/lot-attribute-change-logs/?${params}` : '/lot-attribute-change-logs/'
  const response = await api.get(url)
  return response.data.results || response.data
}
