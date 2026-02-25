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

export const shipSalesOrder = async (id: number, data: { ship_date: string; items: Array<{ item_id: number; quantity: number }> }) => {
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

/** Parsed customer PO result for auto-filling Create Sales Order form */
export interface ParsedCustomerPO {
  customer_po_number: string
  customer_name: string
  customer_address: string
  customer_city: string
  customer_state: string
  customer_zip: string
  customer_country: string
  customer_phone: string
  requested_ship_date: string | null
  items: Array<{
    description: string
    quantity_ordered: number
    unit: string
    unit_price: number
    vendor_part_number?: string
    notes?: string
  }>
  warning?: string
  extracted_preview?: string
}

export const parseCustomerPo = async (file: File): Promise<ParsedCustomerPO> => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await axios.post(`${API_BASE_URL}/sales-orders/parse-customer-po/`, formData, {
    headers: { Accept: 'application/json' },
    maxBodyLength: 50 * 1024 * 1024,
    maxContentLength: 50 * 1024 * 1024,
  })
  return response.data
}

/** Upload customer PO PDF for an existing sales order */
export const uploadCustomerPo = async (salesOrderId: number, file: File): Promise<void> => {
  const formData = new FormData()
  formData.append('file', file)
  await axios.post(`${API_BASE_URL}/sales-orders/${salesOrderId}/customer-po/`, formData, {
    headers: { Accept: 'application/json' },
    maxBodyLength: 50 * 1024 * 1024,
    maxContentLength: 50 * 1024 * 1024,
  })
}

