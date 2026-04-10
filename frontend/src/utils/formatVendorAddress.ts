function s(v: unknown): string {
  if (v == null) return ''
  return String(v).trim()
}

/**
 * Single-line display for vendor location (structured fields + legacy `address`).
 * Uses String() so odd API types (number, etc.) never break rendering.
 */
export function formatVendorAddress(v: {
  street_address?: string | null
  address?: string | null
  city?: string | null
  state?: string | null
  zip_code?: string | null
  country?: string | null
}): string {
  const st = s(v.street_address)
  const legacy = s(v.address)
  const city = s(v.city)
  const state = s(v.state)
  const zip = s(v.zip_code)
  const country = s(v.country)

  const parts: string[] = []
  if (st) parts.push(st)
  if (legacy && legacy !== st) parts.push(legacy)
  if (!parts.length && legacy) parts.push(legacy)
  const cityState = [city, state].filter(Boolean).join(', ')
  if (cityState) parts.push(cityState)
  if (zip) parts.push(zip)
  if (country && country !== 'USA') parts.push(country)

  return parts.join(' · ')
}

export function hasVendorAddress(v: {
  street_address?: string | null
  address?: string | null
  city?: string | null
  state?: string | null
  zip_code?: string | null
  country?: string | null
}): boolean {
  return formatVendorAddress(v).length > 0
}

function pickString(obj: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return ''
}

/**
 * Pull address-like fields from SupplierSurvey.company_info (JSON).
 * Used when addresses were saved on the survey during approval but never copied to Vendor.* columns.
 */
export function extractAddressFromCompanyInfo(raw: unknown): {
  street_address?: string
  address?: string
  city?: string
  state?: string
  zip_code?: string
  country?: string
} {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const o = raw as Record<string, unknown>

  const flat = {
    street_address: pickString(o, [
      'street_address',
      'street',
      'street1',
      'street2',
      'address_line_1',
      'address_line1',
      'AddressLine1',
      'addressLine1',
      'line1',
      'line_1',
      'Address1',
      'Addr1',
      'addr1',
      'Street',
      'streetAddress',
      'StreetAddress',
      'facility_street',
      'plant_street',
    ]),
    address: pickString(o, [
      'address',
      'physical_address',
      'company_address',
      'mailing_address',
      'full_address',
      'Address',
      'business_address',
      'vendor_address',
      'facility_address',
      'plant_address',
      'location_address',
      'hq_address',
    ]),
    city: pickString(o, ['city', 'town', 'municipality', 'City', 'locality', 'CityTown']),
    state: pickString(o, ['state', 'province', 'region', 'State', 'StateProvince', 'state_province', 'st']),
    zip_code: pickString(o, ['zip_code', 'zip', 'postal_code', 'postal', 'Zip', 'ZipCode', 'postalCode', 'zipcode']),
    country: pickString(o, ['country', 'Country', 'CountryCode', 'country_code']),
  }

  const hasFlat = Object.values(flat).some(Boolean)
  if (hasFlat) {
    return {
      ...(flat.street_address ? { street_address: flat.street_address } : {}),
      ...(flat.address ? { address: flat.address } : {}),
      ...(flat.city ? { city: flat.city } : {}),
      ...(flat.state ? { state: flat.state } : {}),
      ...(flat.zip_code ? { zip_code: flat.zip_code } : {}),
      ...(flat.country ? { country: flat.country } : {}),
    }
  }

  const nestedKeys = [
    'headquarters',
    'facility',
    'facility_address',
    'location',
    'company_address',
    'mailing_address',
    'physical_address',
    'billing_address',
    'shipping_address',
    'company_info',
    'plant',
    'manufacturing',
    'manufacturing_site',
    'vendor_facility',
    'address_block',
  ]
  for (const nk of nestedKeys) {
    const sub = o[nk]
    if (sub && typeof sub === 'object' && !Array.isArray(sub)) {
      const inner = extractAddressFromCompanyInfo(sub)
      if (Object.keys(inner).length > 0) return inner
    }
  }

  return {}
}

function collectStringsFromJson(obj: unknown, depth: number): string[] {
  if (depth > 8) return []
  if (typeof obj === 'string' && obj.trim()) return [obj.trim()]
  if (!obj || typeof obj !== 'object') return []
  if (Array.isArray(obj)) {
    return obj.flatMap((item) => collectStringsFromJson(item, depth + 1))
  }
  const out: string[] = []
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const lk = k.toLowerCase()
    if (['email', 'phone', 'fax', 'url', 'website'].some((x) => lk.includes(x)) && !lk.includes('address')) continue
    out.push(...collectStringsFromJson(v, depth + 1))
  }
  return out
}

function looksLikeAddressLine(s: string): boolean {
  if (s.length < 6) return false
  if (s.includes('@')) return false
  if (/\d/.test(s) && (s.includes(',') || s.length > 14)) return true
  if ((s.match(/\d/g) || []).length >= 2 && s.length >= 10) return true
  if (/\b(st|street|ave|avenue|rd|road|dr|drive|blvd|suite|ste|unit|box)\b/i.test(s)) return true
  return false
}

/** When structured keys miss (odd questionnaire keys), join address-like strings from JSON. */
export function formatCompanyInfoFallbackFromJson(raw: unknown): string {
  if (!raw || typeof raw !== 'object') return ''
  const all = collectStringsFromJson(raw, 0)
  const seen = new Set<string>()
  const candidates: string[] = []
  for (const t of all) {
    if (!looksLikeAddressLine(t) || seen.has(t)) continue
    seen.add(t)
    candidates.push(t)
    if (candidates.length >= 6) break
  }
  return candidates.join(' · ')
}

export type VendorWithSurveyAddress = {
  /** Set by API (VendorSerializer) — always prefer this when present */
  display_address?: string | null
  street_address?: string | null
  address?: string | null
  city?: string | null
  state?: string | null
  zip_code?: string | null
  country?: string | null
  notes?: string | null
  survey?: {
    company_info?: Record<string, unknown>
    compliance_responses?: Record<string, unknown>
    quality_program_responses?: Record<string, unknown>
    food_security_responses?: Record<string, unknown>
    see_program_responses?: Record<string, unknown>
  } | null
}

const SURVEY_JSON_BLOB_KEYS = [
  'company_info',
  'compliance_responses',
  'quality_program_responses',
  'food_security_responses',
  'see_program_responses',
] as const

function iterSurveyJsonBlobs(survey: VendorWithSurveyAddress['survey']): Record<string, unknown>[] {
  if (!survey || typeof survey !== 'object') return []
  const out: Record<string, unknown>[] = []
  for (const k of SURVEY_JSON_BLOB_KEYS) {
    const blob = survey[k]
    if (blob && typeof blob === 'object' && !Array.isArray(blob) && Object.keys(blob).length > 0) {
      out.push(blob as Record<string, unknown>)
    }
  }
  return out
}

/**
 * Prefer server-built display_address; then Vendor fields; then questionnaire JSON blobs.
 */
function fallbackAddressFromNotes(notes: string | null | undefined): string {
  if (!notes || !String(notes).trim()) return ''
  const text = String(notes).trim()
  const addrBlock = /^Address\s*:\s*([^\n]+(?:\n[^\n]+){0,4})/im.exec(text)
  if (addrBlock) {
    const line = addrBlock[1].split(/\n/).map((s) => s.trim()).filter(Boolean).join(' ')
    if (line.length > 5) return line.slice(0, 500)
  }
  const lines = text.split(/\n/).map((s) => s.trim()).filter(Boolean)
  for (let i = 0; i < lines.length; i++) {
    if (/\b\d{5}(?:-\d{4})?\b/.test(lines[i])) {
      return lines.slice(Math.max(0, i - 2), i + 3).join(' · ').slice(0, 500)
    }
  }
  for (const line of lines) {
    if (line.length < 8) continue
    if (/\d/.test(line) && (line.includes(',') || /\b(st|street|ave|rd|drive|suite|ste|unit)\b/i.test(line))) {
      return line.slice(0, 500)
    }
  }
  return ''
}

export function formatVendorAddressWithSurveyFallback(v: VendorWithSurveyAddress | null | undefined): string {
  if (!v) return ''
  const api = v.display_address
  if (typeof api === 'string' && api.trim()) return api.trim()
  const primary = formatVendorAddress(v)
  if (primary) return primary
  const fromNotes = fallbackAddressFromNotes(v.notes)
  if (fromNotes) return fromNotes
  for (const blob of iterSurveyJsonBlobs(v.survey)) {
    const extracted = extractAddressFromCompanyInfo(blob)
    const fromStructured = formatVendorAddress(extracted)
    if (fromStructured) return fromStructured
    const fb = formatCompanyInfoFallbackFromJson(blob)
    if (fb) return fb
  }
  return ''
}

export function hasVendorAddressWithSurveyFallback(v: VendorWithSurveyAddress | null | undefined): boolean {
  return formatVendorAddressWithSurveyFallback(v).length > 0
}
