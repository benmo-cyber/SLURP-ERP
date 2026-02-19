import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const getCostMasters = async () => {
  const response = await api.get('/cost-master/')
  return response.data.results || response.data
}

export const getCostMaster = async (id: number) => {
  const response = await api.get(`/cost-master/${id}/`)
  return response.data
}

export const createCostMaster = async (data: any) => {
  const response = await api.post('/cost-master/', data)
  return response.data
}

export const updateCostMaster = async (id: number, data: any) => {
  const response = await api.put(`/cost-master/${id}/`, data)
  return response.data
}

export const deleteCostMaster = async (id: number) => {
  const response = await api.delete(`/cost-master/${id}/`)
  return response.data
}

export const getCostMasterByProductCode = async (productCode: string, vendor?: string) => {
  let url = `/cost-master/?product_code=${productCode}`
  if (vendor) {
    url += `&vendor=${encodeURIComponent(vendor)}`
  }
  const response = await api.get(url)
  const data = response.data.results || response.data
  return Array.isArray(data) && data.length > 0 ? data[0] : null
}

export const getPricingHistory = async (productCodes: string[]) => {
  const params = productCodes.map(code => `product_code=${code}`).join('&')
  const response = await api.get(`/cost-master/pricing_history/?${params}`)
  return response.data
}

export const getCostMasterHistory = async (costMasterId: number) => {
  const response = await api.get(`/cost-master/${costMasterId}/history/`)
  return response.data
}


export const refreshTariffs = async () => {
  const response = await api.post('/cost-master/refresh_tariffs/')
  return response.data
}
