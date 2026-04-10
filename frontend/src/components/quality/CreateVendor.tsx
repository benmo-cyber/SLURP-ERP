import { useState } from 'react'
import { createVendor } from '../../api/quality'
import { VendorAddressFields } from './VendorAddressFields'
import './CreateVendor.css'

/** DRF returns field errors (e.g. duplicate name), not always `detail`. */
function formatApiError(err: unknown): string {
  const e = err as { response?: { data?: Record<string, unknown> }; message?: string }
  const d = e?.response?.data
  if (!d) return e?.message || 'Request failed'
  if (typeof d === 'string') return d
  if (typeof d.error === 'string') return d.error
  if (typeof d.detail === 'string') return d.detail
  if (Array.isArray(d.detail)) return JSON.stringify(d.detail)
  if (typeof d.message === 'string') return d.message
  if (Array.isArray(d.non_field_errors)) return (d.non_field_errors as string[]).join(' ')
  const parts: string[] = []
  for (const [key, val] of Object.entries(d)) {
    if (['detail', 'message', 'error', 'non_field_errors'].includes(key)) continue
    if (Array.isArray(val)) parts.push(`${key}: ${val.join(', ')}`)
    else if (val != null) parts.push(`${key}: ${String(val)}`)
  }
  if (parts.length) return parts.join('; ')
  try {
    return JSON.stringify(d)
  } catch {
    return 'Request failed'
  }
}

interface CreateVendorProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateVendor({ onClose, onSuccess }: CreateVendorProps) {
  const [formData, setFormData] = useState({
    name: '',
    vendor_id: '',
    contact_name: '',
    email: '',
    phone: '',
    street_address: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'USA',
    risk_profile: '2',
    notes: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name) {
      alert('Please enter vendor name')
      return
    }

    try {
      setSubmitting(true)
      
      await createVendor({
        name: formData.name,
        vendor_id: formData.vendor_id || null,
        contact_name: formData.contact_name || null,
        email: formData.email || null,
        phone: formData.phone || null,
        street_address: formData.street_address || null,
        address: formData.address || null,
        city: formData.city || null,
        state: formData.state || null,
        zip_code: formData.zip_code || null,
        country: formData.country || 'USA',
        risk_profile: formData.risk_profile,
        approval_status: 'pending',
        notes: formData.notes || null,
      })
      
      alert('Vendor created successfully!')
      onSuccess()
    } catch (error: unknown) {
      console.error('Failed to create vendor:', error)
      alert(formatApiError(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content vendor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add New Vendor</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="vendor-form">
          <div className="form-row">
            <div className="form-group">
              <label>Vendor Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Vendor ID</label>
              <input
                type="text"
                value={formData.vendor_id}
                onChange={(e) => setFormData({ ...formData, vendor_id: e.target.value })}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Contact Name</label>
              <input
                type="text"
                value={formData.contact_name}
                onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Phone</label>
              <input
                type="text"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Risk Profile *</label>
              <select
                value={formData.risk_profile}
                onChange={(e) => setFormData({ ...formData, risk_profile: e.target.value })}
                required
              >
                <option value="1">1 - Low Risk</option>
                <option value="2">2 - Medium Risk</option>
                <option value="3">3 - High Risk</option>
              </select>
            </div>
          </div>

          <VendorAddressFields
            idPrefix="create-vendor"
            values={{
              street_address: formData.street_address,
              address: formData.address,
              city: formData.city,
              state: formData.state,
              zip_code: formData.zip_code,
              country: formData.country,
            }}
            onChange={(patch) => setFormData({ ...formData, ...patch })}
          />

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
              placeholder="Additional notes about the vendor"
            />
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Vendor'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateVendor





