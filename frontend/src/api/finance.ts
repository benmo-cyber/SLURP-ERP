import axios from 'axios'
import { getItems } from './inventory'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Re-export getItems for convenience
export { getItems }

// Customer Pricing API
export const getCustomerPricing = async () => {
  const response = await api.get('/customer-pricing/')
  return response.data.results || response.data
}

export const createCustomerPricing = async (data: any) => {
  const response = await api.post('/customer-pricing/', data)
  return response.data
}

// Vendor Pricing API
export const getVendorPricing = async () => {
  const response = await api.get('/vendor-pricing/')
  return response.data.results || response.data
}

export const createVendorPricing = async (data: any) => {
  const response = await api.post('/vendor-pricing/', data)
  return response.data
}

// Invoices API
export const getInvoices = async () => {
  const response = await api.get('/invoices/')
  return response.data.results || response.data
}

export const getInvoice = async (id: number) => {
  const response = await api.get(`/invoices/${id}/`)
  return response.data
}

export const createInvoice = async (data: any) => {
  const response = await api.post('/invoices/', data)
  return response.data
}

export const updateInvoice = async (id: number, data: any) => {
  const response = await api.put(`/invoices/${id}/`, data)
  return response.data
}

// Accounts API
export const getAccounts = async () => {
  const response = await api.get('/accounts/')
  return response.data.results || response.data
}

export const getAccount = async (id: number) => {
  const response = await api.get(`/accounts/${id}/`)
  return response.data
}

export const createAccount = async (data: any) => {
  const response = await api.post('/accounts/', data)
  return response.data
}

export const updateAccount = async (id: number, data: any) => {
  const response = await api.put(`/accounts/${id}/`, data)
  return response.data
}

// Journal Entries API
export const getJournalEntries = async () => {
  const response = await api.get('/journal-entries/')
  return response.data.results || response.data
}

export const getJournalEntry = async (id: number) => {
  const response = await api.get(`/journal-entries/${id}/`)
  return response.data
}

export const createJournalEntry = async (data: any) => {
  const response = await api.post('/journal-entries/', data)
  return response.data
}

export const updateJournalEntry = async (id: number, data: any) => {
  const response = await api.put(`/journal-entries/${id}/`, data)
  return response.data
}

// Financial Reports API
export const getTrialBalance = async () => {
  const response = await api.get('/trial-balance/')
  return response.data
}

export const getBalanceSheet = async () => {
  const response = await api.get('/balance-sheet/')
  return response.data
}

export const getIncomeStatement = async () => {
  const response = await api.get('/income-statement/')
  return response.data
}
