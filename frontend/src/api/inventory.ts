import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Items API
export const getItems = async () => {
  const response = await api.get('/items/')
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
  const response = await api.post('/lots/', {
    item_id: data.item_id,
    quantity: data.quantity,
    quantity_remaining: data.quantity,
    received_date: data.received_date,
    expiration_date: data.expiration_date,
  })
  return response.data
}

// Production Batches API
export const getProductionBatches = async () => {
  const response = await api.get('/production-batches/')
  // Handle paginated response
  return response.data.results || response.data
}

export const createProductionBatch = async (data: any) => {
  const response = await api.post('/production-batches/', data)
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

