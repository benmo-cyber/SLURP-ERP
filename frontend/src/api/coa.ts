import { api } from './client'

export type CoaReleasePreview = {
  full_clear_from_hold: boolean
  coa_required: boolean
  template_lines: ItemCoaTestLine[]
  formula_qc: {
    qc_parameter_name: string
    qc_spec_min: number | null
    qc_spec_max: number | null
  } | null
}

export type ItemCoaTestLine = {
  id: number
  item: number
  sort_order: number
  test_name: string
  specification_text: string
  result_kind: string
  numeric_min: number | null
  numeric_max: number | null
}

export type LotCoaCertificateRow = {
  id: number
  lot: number
  lot_number: string
  item_sku: string
  item_name: string
  customer_name: string
  customer_po: string
  issued_at: string
  coa_pdf_url: string | null
}

export const coaReleasePreview = async (lotId: number, releaseQty: number): Promise<CoaReleasePreview> => {
  const response = await api.get(`/lots/${lotId}/coa_release_preview/`, {
    params: { release_qty: releaseQty },
  })
  return response.data
}

export const getItemCoaTestLines = async (itemId: number): Promise<ItemCoaTestLine[]> => {
  const response = await api.get('/item-coa-test-lines/', { params: { item: itemId } })
  return response.data.results || response.data
}

export const createItemCoaTestLine = async (data: Partial<ItemCoaTestLine> & { item: number }) => {
  const response = await api.post('/item-coa-test-lines/', data)
  return response.data
}

export const updateItemCoaTestLine = async (id: number, data: Partial<ItemCoaTestLine>) => {
  const response = await api.patch(`/item-coa-test-lines/${id}/`, data)
  return response.data
}

export const deleteItemCoaTestLine = async (id: number) => {
  await api.delete(`/item-coa-test-lines/${id}/`)
}

export const getLotCoaCertificates = async (params?: { item?: number; sku?: string }) => {
  const response = await api.get('/lot-coa-certificates/', { params })
  return response.data.results || response.data
}

export type LotCoaCustomerCopyRow = {
  id: number
  lot_number: string
  item_sku: string
  item_name: string
  so_number: string
  customer_name: string
  customer_po: string
  quantity_snapshot: number
  coa_pdf_url: string | null
  created_at: string
}

export const getLotCoaCustomerCopies = async (params?: { item?: number; sku?: string; so?: string }) => {
  const response = await api.get('/lot-coa-customer-copies/', { params })
  return response.data.results || response.data
}
