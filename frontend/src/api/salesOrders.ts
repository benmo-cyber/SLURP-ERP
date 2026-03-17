import { api, API_BASE_URL } from './client'

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

/** Partial update (e.g. ship date only). Use this when updating a single field to avoid 400 from PUT. */
export const patchSalesOrder = async (id: number, data: Record<string, unknown>) => {
  const response = await api.patch(`/sales-orders/${id}/`, data)
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

export const shipSalesOrder = async (
  id: number,
  data: {
    ship_date: string
    items: Array<{ item_id: number; quantity: number }>
    dimensions?: string
    pieces?: number
    tracking_number?: string
    carrier?: string
  }
) => {
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

/** Packing list URL for a sales order (open in new tab; same pattern as invoice PDF). */
export const getPackingListUrl = (salesOrderId: number) =>
  `${API_BASE_URL.replace(/\/$/, '')}/sales-orders/${salesOrderId}/packing-list/`

/** Open packing list for a sales order in a new tab (same pattern as invoice PDF). */
export const openPackingList = async (salesOrderId: number): Promise<void> => {
  window.open(getPackingListUrl(salesOrderId), '_blank', 'noopener,noreferrer')
}

/** Packing list URL for a specific shipment (one PDF per release). */
export const getPackingListUrlForShipment = (shipmentId: number) =>
  `${API_BASE_URL.replace(/\/$/, '')}/shipments/${shipmentId}/packing-list/`

/** Open packing list for a shipment in a new tab. */
export const openPackingListForShipment = (shipmentId: number): void => {
  window.open(getPackingListUrlForShipment(shipmentId), '_blank', 'noopener,noreferrer')
}

/** Fetch shipments for a sales order (optional; invoice may already include sales_order.shipments). */
export const getShipments = async (salesOrderId: number) => {
  const response = await api.get(`/shipments/?sales_order=${salesOrderId}`)
  return response.data.results ?? response.data
}

export const getAvailableSalesOrders = async () => {
  // Get all sales orders and filter for issued or ready_for_shipment with allocations
  const response = await api.get('/sales-orders/')
  const allOrders = response.data.results || response.data
  return allOrders.filter((so: any) => {
    // Must be issued or ready for shipment (backend sets ready_for_shipment when fully allocated)
    if (so.status !== 'issued' && so.status !== 'ready_for_shipment') return false
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

