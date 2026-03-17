import { api, API_BASE_URL } from './client'

export const getPurchaseOrders = async (params?: { status?: string }) => {
  const response = await api.get('/purchase-orders/', { params })
  return response.data.results || response.data
}

export const getPurchaseOrder = async (id: number) => {
  const response = await api.get(`/purchase-orders/${id}/`)
  return response.data
}

export const createPurchaseOrder = async (data: any) => {
  const response = await api.post('/purchase-orders/', data)
  return response.data
}

export const updatePurchaseOrder = async (id: number, data: any, partial = true) => {
  const method = partial ? 'patch' : 'put'
  const response = await api.request({ method, url: `/purchase-orders/${id}/`, data })
  return response.data
}

export const issuePurchaseOrder = async (id: number) => {
  const response = await api.post(`/purchase-orders/${id}/issue/`)
  return response.data
}

export const receivePurchaseOrder = async (id: number) => {
  const response = await api.post(`/purchase-orders/${id}/receive/`)
  return response.data
}

export const revisePurchaseOrder = async (id: number) => {
  const response = await api.post(`/purchase-orders/${id}/revise/`)
  return response.data
}

export const cancelPurchaseOrder = async (id: number) => {
  const response = await api.post(`/purchase-orders/${id}/cancel/`)
  return response.data
}

export const deletePurchaseOrder = async (id: number) => {
  const response = await api.delete(`/purchase-orders/${id}/`)
  return response.data
}

export const updateDeliveryFromTracking = async (id: number, trackingNumber: string, carrier: string) => {
  const response = await api.post(`/purchase-orders/${id}/update-delivery-from-tracking/`, {
    tracking_number: trackingNumber,
    carrier: carrier
  })
  return response.data
}

export const getPurchaseOrderPdfUrl = (poId: number) => {
  return `${API_BASE_URL}/purchase-orders/${poId}/pdf/`
}

