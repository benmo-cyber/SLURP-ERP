import { api } from './client'

export type AddressSuggestion = {
  label: string
  street_address: string
  address: string
  city: string
  state: string
  zip_code: string
  country: string
}

/** Address suggestions via Django proxy (Mapbox when configured, else Nominatim). Min ~3 characters. */
export async function fetchAddressSuggestions(
  q: string,
  country?: string
): Promise<AddressSuggestion[]> {
  const t = q.trim()
  if (t.length < 3) return []
  const c = country?.trim()
  const params: Record<string, string> = { q: t }
  if (c) params.country = c
  const { data } = await api.get<AddressSuggestion[]>('/address-suggest/', { params })
  return Array.isArray(data) ? data : []
}
