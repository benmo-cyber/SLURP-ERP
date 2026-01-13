import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

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
