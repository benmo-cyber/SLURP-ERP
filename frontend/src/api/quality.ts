import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Vendors API
export const getVendors = async () => {
  const response = await api.get('/vendors/')
  // Handle paginated response
  return response.data.results || response.data
}

export const getVendor = async (id: number) => {
  const response = await api.get(`/vendors/${id}/`)
  return response.data
}

export const createVendor = async (data: any) => {
  const response = await api.post('/vendors/', data)
  return response.data
}

export const updateVendor = async (id: number, data: any) => {
  const response = await api.put(`/vendors/${id}/`, data)
  return response.data
}

export const deleteVendor = async (id: number) => {
  const response = await api.delete(`/vendors/${id}/`)
  return response.data
}

export const approveVendor = async (id: number, approvedBy: string = 'DOOF') => {
  const response = await api.post(`/vendors/${id}/approve/`, { approved_by: approvedBy })
  return response.data
}

export const getVendorItems = async (vendorId: number) => {
  const response = await api.get(`/vendors/${vendorId}/items/`)
  return response.data
}

// Vendor History API
export const addVendorHistory = async (vendorId: number, data: any) => {
  const response = await api.post(`/vendors/${vendorId}/history/`, data)
  return response.data
}

export const getVendorHistory = async (vendorId: number) => {
  const response = await api.get(`/vendors/${vendorId}/history/`)
  return response.data.results || response.data
}

// Supplier Survey API
export const getSupplierSurvey = async (vendorId: number) => {
  const response = await api.get(`/supplier-surveys/?vendor=${vendorId}`)
  return response.data.results?.[0] || response.data[0] || null
}

export const createSupplierSurvey = async (data: any) => {
  const response = await api.post('/supplier-surveys/', data)
  return response.data
}

export const updateSupplierSurvey = async (id: number, data: any) => {
  const response = await api.put(`/supplier-surveys/${id}/`, data)
  return response.data
}

export const submitSupplierSurvey = async (id: number) => {
  const response = await api.post(`/supplier-surveys/${id}/submit/`)
  return response.data
}

export const approveSupplierSurvey = async (id: number, data: any) => {
  const response = await api.post(`/supplier-surveys/${id}/approve/`, data)
  return response.data
}

// Supplier Document API
export const getSupplierDocuments = async (vendorId: number) => {
  const response = await api.get(`/supplier-documents/?vendor=${vendorId}`)
  return response.data.results || response.data
}

export const createSupplierDocument = async (data: FormData) => {
  const response = await api.post('/supplier-documents/', data, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

export const updateSupplierDocument = async (id: number, data: any) => {
  const response = await api.put(`/supplier-documents/${id}/`, data)
  return response.data
}

export const deleteSupplierDocument = async (id: number) => {
  const response = await api.delete(`/supplier-documents/${id}/`)
  return response.data
}

// Temporary Exception API
export const getTemporaryExceptions = async (vendorId: number) => {
  const response = await api.get(`/temporary-exceptions/?vendor=${vendorId}`)
  return response.data.results || response.data
}

export const createTemporaryException = async (data: any) => {
  const response = await api.post('/temporary-exceptions/', data)
  return response.data
}

export const updateTemporaryException = async (id: number, data: any) => {
  const response = await api.put(`/temporary-exceptions/${id}/`, data)
  return response.data
}

export const approveTemporaryException = async (id: number, data: any) => {
  const response = await api.post(`/temporary-exceptions/${id}/approve/`, data)
  return response.data
}
