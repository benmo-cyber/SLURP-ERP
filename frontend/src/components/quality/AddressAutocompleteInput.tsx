import { useEffect, useRef, useState } from 'react'
import { fetchAddressSuggestions, type AddressSuggestion } from '../../api/addressSuggest'
import './AddressAutocompleteInput.css'

type Props = {
  id: string
  value: string
  onChange: (value: string) => void
  /** Fills structured fields when user picks a suggestion (street + city + …). */
  onPickSuggestion: (s: AddressSuggestion) => void
  /** When set, Nominatim results are limited to this country (name or ISO code). */
  countryFilter?: string
  placeholder?: string
  autoComplete?: string
}

const DEBOUNCE_MS = 450

/**
 * Typeahead for address line 1 — server proxies Mapbox Geocoding when configured, else OpenStreetMap Nominatim.
 */
export function AddressAutocompleteInput({
  id,
  value,
  onChange,
  onPickSuggestion,
  countryFilter = '',
  placeholder,
  autoComplete = 'address-line1',
}: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<AddressSuggestion[]>([])
  const wrapRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastQueryRef = useRef('')

  const countryTrim = countryFilter.trim()

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = value.trim()
    if (!countryTrim) {
      setItems([])
      setOpen(false)
      setLoading(false)
      return
    }
    if (q.length < 3) {
      setItems([])
      setOpen(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      lastQueryRef.current = q
      setLoading(true)
      try {
        const r = await fetchAddressSuggestions(q, countryTrim)
        if (lastQueryRef.current !== q) return
        setItems(r)
        setOpen(r.length > 0)
      } catch {
        setItems([])
        setOpen(false)
      } finally {
        setLoading(false)
      }
    }, DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [value, countryTrim])

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  return (
    <div className="address-autocomplete-wrap" ref={wrapRef}>
      <div className="address-autocomplete-input-row">
        <input
          id={id}
          type="text"
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => items.length > 0 && setOpen(true)}
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={`${id}-listbox`}
        />
        {loading && <span className="address-autocomplete-spinner" aria-hidden />}
      </div>
      {!countryTrim && (
        <p className="address-autocomplete-country-hint" role="note">
          Enter <strong>country</strong> above first to enable suggestions — you can still type the street address
          manually.
        </p>
      )}
      {open && items.length > 0 && (
        <ul id={`${id}-listbox`} className="address-autocomplete-list" role="listbox">
          {items.map((s, i) => (
            <li
              key={`${s.label}-${i}`}
              role="option"
              className="address-autocomplete-item"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onPickSuggestion(s)
                setOpen(false)
              }}
            >
              <span className="address-autocomplete-item-label">{s.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
