import { api, API_BASE_URL } from './client'

export const getInvoices = async (params?: {
  status?: string
  customer_id?: number
  start_date?: string
  end_date?: string
}) => {
  const response = await api.get('/invoices/', { params })
  return response.data.results || response.data
}

export const getInvoice = async (id: number) => {
  const response = await api.get(`/invoices/${id}/`)
  return response.data
}

export const updateInvoice = async (id: number, data: any) => {
  const response = await api.put(`/invoices/${id}/`, data)
  return response.data
}

export const getAgingReport = async () => {
  const response = await api.get('/invoices/aging-report/')
  return response.data
}

export const getInvoicePdfUrl = (invoiceId: number) => {
  return `${API_BASE_URL}/invoices/${invoiceId}/pdf/`
}