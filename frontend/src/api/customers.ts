import { api } from './client'

// Customers API
export const getCustomers = async (isActive?: boolean) => {
  try {
    const params = isActive !== undefined ? `?is_active=${isActive}` : ''
    const response = await api.get(`/customers/${params}`)
    // Handle both paginated and non-paginated responses
    if (Array.isArray(response.data)) {
      return response.data
    }
    return response.data.results || response.data || []
  } catch (error: any) {
    // If 500 error, return empty array instead of throwing
    if (error.response?.status === 500) {
      console.warn('Customer table may not exist yet. Returning empty array.')
      return []
    }
    throw error
  }
}

export const getCustomer = async (id: number) => {
  const response = await api.get(`/customers/${id}/`)
  return response.data
}

export const createCustomer = async (data: any) => {
  const response = await api.post('/customers/', data)
  return response.data
}

export const updateCustomer = async (id: number, data: any) => {
  const response = await api.put(`/customers/${id}/`, data)
  return response.data
}

export const deleteCustomer = async (id: number) => {
  const response = await api.delete(`/customers/${id}/`)
  return response.data
}

// Customer Pricing API
// currentOnly: when true, only returns pricing effective today and not expired (e.g. for sales order entry)
// Follows all pagination pages — default PAGE_SIZE is 100; large customers otherwise miss SKUs on page 2+.
export const getCustomerPricing = async (customerId?: number, itemId?: number, currentOnly?: boolean) => {
  const base = new URLSearchParams()
  if (customerId) base.append('customer_id', customerId.toString())
  if (itemId) base.append('item_id', itemId.toString())
  base.append('is_active', 'true')
  if (currentOnly) base.append('current_only', 'true')

  const all: unknown[] = []
  let page = 1
  for (;;) {
    const params = new URLSearchParams(base.toString())
    params.set('page', String(page))
    const response = await api.get(`/customer-pricing/?${params.toString()}`)
    const data = response.data
    if (Array.isArray(data)) {
      all.push(...data)
      break
    }
    const results = (data && (data as { results?: unknown[] }).results) || []
    all.push(...results)
    const next = data && (data as { next?: string | null }).next
    if (!next || results.length === 0) break
    page += 1
    if (page > 500) break
  }
  return all
}

export const createCustomerPricing = async (data: any) => {
  const response = await api.post('/customer-pricing/', data)
  return response.data
}

export const updateCustomerPricing = async (id: number, data: any) => {
  const response = await api.put(`/customer-pricing/${id}/`, data)
  return response.data
}

export const deleteCustomerPricing = async (id: number) => {
  const response = await api.delete(`/customer-pricing/${id}/`)
  return response.data
}

// Ship-To Locations API
export const getShipToLocations = async (customerId?: number) => {
  const params = customerId ? `?customer_id=${customerId}` : ''
  const response = await api.get(`/ship-to-locations/${params}`)
  return response.data.results || response.data
}

export const getShipToLocation = async (id: number) => {
  const response = await api.get(`/ship-to-locations/${id}/`)
  return response.data
}

export const createShipToLocation = async (data: any) => {
  const response = await api.post('/ship-to-locations/', data)
  return response.data
}

export const updateShipToLocation = async (id: number, data: any) => {
  const response = await api.put(`/ship-to-locations/${id}/`, data)
  return response.data
}

export const deleteShipToLocation = async (id: number) => {
  const response = await api.delete(`/ship-to-locations/${id}/`)
  return response.data
}

// Customer Contacts API
export const getCustomerContacts = async (customerId?: number) => {
  const params = customerId ? `?customer_id=${customerId}` : ''
  const response = await api.get(`/customer-contacts/${params}`)
  return response.data.results || response.data
}

export const createCustomerContact = async (data: any) => {
  const response = await api.post('/customer-contacts/', data)
  return response.data
}

export const updateCustomerContact = async (id: number, data: any) => {
  const response = await api.put(`/customer-contacts/${id}/`, data)
  return response.data
}

export const deleteCustomerContact = async (id: number) => {
  const response = await api.delete(`/customer-contacts/${id}/`)
  return response.data
}

// Sales Calls API
export const getSalesCalls = async (customerId?: number) => {
  const params = customerId ? `?customer_id=${customerId}` : ''
  const response = await api.get(`/sales-calls/${params}`)
  return response.data.results || response.data
}

export const createSalesCall = async (data: any) => {
  const response = await api.post('/sales-calls/', data)
  return response.data
}

export const updateSalesCall = async (id: number, data: any) => {
  const response = await api.put(`/sales-calls/${id}/`, data)
  return response.data
}

export const deleteSalesCall = async (id: number) => {
  const response = await api.delete(`/sales-calls/${id}/`)
  return response.data
}

// Customer Forecasts API
export const getCustomerForecasts = async (customerId?: number) => {
  const params = customerId ? `?customer_id=${customerId}` : ''
  const response = await api.get(`/customer-forecasts/${params}`)
  return response.data.results || response.data
}

export const createCustomerForecast = async (data: any) => {
  const response = await api.post('/customer-forecasts/', data)
  return response.data
}

export const updateCustomerForecast = async (id: number, data: any) => {
  const response = await api.put(`/customer-forecasts/${id}/`, data)
  return response.data
}

export const deleteCustomerForecast = async (id: number) => {
  const response = await api.delete(`/customer-forecasts/${id}/`)
  return response.data
}

// Customer Usage API
export const getCustomerUsage = async (customerId: number, itemId?: number, year?: number) => {
  const params = new URLSearchParams()
  params.append('customer_id', customerId.toString())
  if (itemId) params.append('item_id', itemId.toString())
  if (year) params.append('year', year.toString())
  const response = await api.get(`/customer-usage/?${params}`)
  return response.data
}