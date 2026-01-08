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
  if (data.short_reason && data.short_reason.trim()) payload.short_reason = data.short_reason.trim()
  
  console.log('API payload:', payload)
  const response = await api.post('/lots/', payload)
  return response.data
}

export const reverseCheckIn = async (lotId: number) => {
  const response = await api.post(`/lots/${lotId}/reverse-check-in/`)
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
  const response = await api.put(`/production-batches/${id}/`, data)
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

export const createFormula = async (data: any) => {
  const response = await api.post('/formulas/', data)
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
  const response = await api.get(`/lots/lots_by_sku_vendor/?${params}`)
  return response.data
}
