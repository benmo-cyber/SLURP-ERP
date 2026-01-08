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



