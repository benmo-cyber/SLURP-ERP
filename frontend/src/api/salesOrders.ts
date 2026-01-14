import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const getSalesOrders = async () => {
  const response = await api.get('/sales-orders/')
  return response.data.results || response.data
}

export const getSalesOrder = async (id: number) => {
  const response = await api.get(`/sales-orders/${id}/`)
  return response.data
}

export const createSalesOrder = async (data: any) => {
  const response = await api.post('/sales-orders/', data)
  return response.data
}

export const updateSalesOrder = async (id: number, data: any) => {
  const response = await api.put(`/sales-orders/${id}/`, data)
  return response.data
}

export const deleteSalesOrder = async (id: number) => {
  const response = await api.delete(`/sales-orders/${id}/`)
  return response.data
}

export const allocateSalesOrder = async (id: number, data: any) => {
  const response = await api.post(`/sales-orders/${id}/allocate/`, data)
  return response.data
}

export const shipSalesOrder = async (id: number, data: { ship_date: string; invoice_date?: string; tracking_number: string }) => {
  const response = await api.post(`/sales-orders/${id}/ship/`, data)
  return response.data
}

export const cancelSalesOrder = async (id: number) => {
  const response = await api.post(`/sales-orders/${id}/cancel/`)
  return response.data
}

export const issueSalesOrder = async (id: number) => {
  const response = await api.post(`/sales-orders/${id}/issue/`)
  return response.data
}

export const getAvailableSalesOrders = async () => {
  // Get all sales orders and filter for issued orders with allocations
  const response = await api.get('/sales-orders/')
  const allOrders = response.data.results || response.data
  return allOrders.filter((so: any) => {
    // Must be issued
    if (so.status !== 'issued') return false
    // Must have at least one item with allocation
    if (!so.items || so.items.length === 0) return false
    return so.items.some((item: any) => item.quantity_allocated > 0)
  })
}

