import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Items API
export const getItems = async (approvedVendorsOnly: boolean = false) => {
  const url = approvedVendorsOnly ? '/items/?approved_vendors_only=true' : '/items/'
  const response = await api.get(url)
  // Handle paginated response
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
  const response = await api.put(`/items/${id}/`, data)
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
  
  // Add optional fields only if they exist
  if (data.expiration_date) payload.expiration_date = data.expiration_date
  if (data.freight_actual) payload.freight_actual = parseFloat(data.freight_actual) || null
  if (data.po_number) payload.po_number = data.po_number
  if (data.vendor_lot_number) payload.vendor_lot_number = data.vendor_lot_number
  if (data.short_reason && data.short_reason.trim()) payload.short_reason = data.short_reason.trim()
  
  console.log('API payload:', payload)
  const response = await api.post('/lots/', payload)
  return response.data
}

export const reverseCheckIn = async (lotId: number) => {
  const response = await api.post(`/lots/${lotId}/reverse-check-in/`)
  return response.data
}

export const updateLot = async (lotId: number, data: any) => {
  const response = await api.patch(`/lots/${lotId}/`, data)
  return response.data
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
export const getInventoryDetails = async () => {
  const response = await api.get('/lots/inventory_details/')
  return response.data
}

// Get lots by SKU and vendor
export const getLotsBySkuVendor = async (sku: string, vendor?: string) => {
  const params = new URLSearchParams({ sku })
  if (vendor) {
    params.append('vendor', vendor)
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
  transaction_type: 'receipt' | 'production_input' | 'production_output' | 'sale' | 'adjustment' | 'allocation' | 'deallocation' | 'manual' | 'reversal'
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
