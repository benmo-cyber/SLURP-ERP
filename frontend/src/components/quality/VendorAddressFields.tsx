import { AddressAutocompleteInput } from './AddressAutocompleteInput'
import './VendorAddressFields.css'

export type VendorAddressFormValues = {
  street_address: string
  /** Extra lines, district, building name — maps to legacy `address` on Vendor */
  address: string
  city: string
  state: string
  zip_code: string
  country: string
}

type Props = {
  values: VendorAddressFormValues
  onChange: (patch: Partial<VendorAddressFormValues>) => void
  idPrefix?: string
}

/**
 * Labels and layout tuned for US and international addresses (postcode, prefecture, county, etc.).
 */
export function VendorAddressFields({ values, onChange, idPrefix = 'va' }: Props) {
  const v = values
  return (
    <fieldset className="vendor-address-fieldset">
      <legend className="vendor-address-legend">Facility / mailing address</legend>
      <p className="vendor-address-intl-hint">
        Enter <strong>country</strong> first — street suggestions are scoped to that country. Use{' '}
        <strong>address line 1</strong> for street-level search, or type everything manually. Non‑U.S. formats vary:
        leave <strong>state / province</strong> blank if it does not apply. Use <strong>line 2</strong> for building,
        district, or ward. <strong>Postal code</strong> covers ZIP, postcode, PIN, etc.
      </p>

      <div className="form-group">
        <label htmlFor={`${idPrefix}-country`}>Country</label>
        <input
          id={`${idPrefix}-country`}
          type="text"
          autoComplete="country-name"
          placeholder="e.g. United States, DE, Germany, United Kingdom"
          value={v.country}
          onChange={(e) => onChange({ country: e.target.value })}
        />
        <small className="form-hint">
          Common English names or two-letter codes (US, GB, DE) — used to narrow address line 1 suggestions.
        </small>
      </div>

      <div className="form-group">
        <label htmlFor={`${idPrefix}-line1`}>Address line 1</label>
        <AddressAutocompleteInput
          id={`${idPrefix}-line1`}
          value={v.street_address}
          countryFilter={v.country}
          onChange={(street_address) => onChange({ street_address })}
          onPickSuggestion={(s) =>
            onChange({
              street_address: s.street_address || '',
              address: s.address || '',
              city: s.city || '',
              state: s.state || '',
              zip_code: s.zip_code || '',
              country: (s.country && s.country.trim()) || v.country,
            })
          }
          placeholder="Street, place, or postal code — pick a suggestion or keep typing"
        />
        <small className="form-hint">
          Suggestions require country above; choosing a row fills city, postal code, and country when available —
          you can edit any field afterward.
        </small>
      </div>

      <div className="form-group">
        <label htmlFor={`${idPrefix}-line2`}>Address line 2 (optional)</label>
        <textarea
          id={`${idPrefix}-line2`}
          rows={2}
          autoComplete="address-line2"
          placeholder="Building, floor, suite, district, ward, unit, or second line as used locally"
          value={v.address}
          onChange={(e) => onChange({ address: e.target.value })}
        />
      </div>

      <div className="form-row vendor-address-row-triple">
        <div className="form-group">
          <label htmlFor={`${idPrefix}-city`}>City / town / locality</label>
          <input
            id={`${idPrefix}-city`}
            type="text"
            autoComplete="address-level2"
            placeholder="City, town, or locality"
            value={v.city}
            onChange={(e) => onChange({ city: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label htmlFor={`${idPrefix}-state`}>State / province / region</label>
          <input
            id={`${idPrefix}-state`}
            type="text"
            autoComplete="address-level1"
            placeholder="Optional — prefecture, county, canton, emirate, etc."
            value={v.state}
            onChange={(e) => onChange({ state: e.target.value })}
          />
        </div>
      </div>

      <div className="form-group vendor-address-postal-only">
        <label htmlFor={`${idPrefix}-postal`}>Postal code</label>
        <input
          id={`${idPrefix}-postal`}
          type="text"
          autoComplete="postal-code"
          placeholder="ZIP, postcode, PIN, or national code"
          value={v.zip_code}
          onChange={(e) => onChange({ zip_code: e.target.value })}
        />
        <small className="form-hint">Any format; not limited to U.S. ZIP length.</small>
      </div>
    </fieldset>
  )
}
