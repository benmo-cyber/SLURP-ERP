import { api } from './client'

export const getRDFormulas = async () => {
  const response = await api.get('/rd-formulas/')
  return response.data.results ?? response.data
}

export const getRDFormula = async (id: number) => {
  const response = await api.get(`/rd-formulas/${id}/`)
  return response.data
}

export const createRDFormula = async (data: { name: string; status?: string; notes?: string; lines: any[] }) => {
  const response = await api.post('/rd-formulas/', data)
  return response.data
}

export const updateRDFormula = async (id: number, data: { name?: string; status?: string; notes?: string; lines?: any[] }) => {
  const response = await api.patch(`/rd-formulas/${id}/`, data)
  return response.data
}

export const deleteRDFormula = async (id: number) => {
  const response = await api.delete(`/rd-formulas/${id}/`)
  return response.data
}
