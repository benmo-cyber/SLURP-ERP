import { useState } from 'react'
import { createVendor } from '../../api/quality'
import './CreateVendor.css'

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
    address: '',
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
        address: formData.address || null,
        risk_profile: formData.risk_profile,
        approval_status: 'pending',
        notes: formData.notes || null,
      })
      
      alert('Vendor created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create vendor:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create vendor')
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

          <div className="form-group">
            <label>Address</label>
            <textarea
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              rows={3}
            />
          </div>

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





