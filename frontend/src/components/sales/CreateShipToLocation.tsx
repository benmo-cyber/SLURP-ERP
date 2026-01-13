import { useState, useEffect } from 'react'
import { getCustomers } from '../../api/customers'
import { createShipToLocation, updateShipToLocation } from '../../api/customers'
import './CreateShipToLocation.css'

interface CreateShipToLocationProps {
  customerId: number
  location?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateShipToLocation({ customerId, location, onClose, onSuccess }: CreateShipToLocationProps) {
  const [formData, setFormData] = useState({
    location_name: location?.location_name || '',
    contact_name: location?.contact_name || '',
    email: location?.email || '',
    phone: location?.phone || '',
    address: location?.address || '',
    city: location?.city || '',
    state: location?.state || '',
    zip_code: location?.zip_code || '',
    country: location?.country || 'USA',
    is_default: location?.is_default || false,
    is_active: location?.is_active !== undefined ? location.is_active : true,
    notes: location?.notes || '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.location_name || !formData.address || !formData.city || !formData.zip_code) {
      alert('Please fill in all required fields (Location Name, Address, City, Zip Code)')
      return
    }

    try {
      if (location) {
        await updateShipToLocation(location.id, { ...formData, customer: customerId })
        alert('Ship-to location updated successfully!')
      } else {
        await createShipToLocation({ ...formData, customer: customerId })
        alert('Ship-to location created successfully!')
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to save ship-to location:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save ship-to location')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-shipto-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{location ? 'Edit Ship-To Location' : 'Add Ship-To Location'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="shipto-form">
          <div className="form-group">
            <label>Location Name *</label>
            <input
              type="text"
              value={formData.location_name}
              onChange={(e) => setFormData({ ...formData, location_name: e.target.value })}
              required
              placeholder="e.g., Main Warehouse, West Coast Facility"
            />
          </div>

          <div className="form-group">
            <label>Contact Name</label>
            <input
              type="text"
              value={formData.contact_name}
              onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Phone</label>
              <input
                type="text"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label>Address *</label>
            <textarea
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              required
              rows={2}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>City *</label>
              <input
                type="text"
                value={formData.city}
                onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>State</label>
              <input
                type="text"
                value={formData.state}
                onChange={(e) => setFormData({ ...formData, state: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>Zip Code *</label>
              <input
                type="text"
                value={formData.zip_code}
                onChange={(e) => setFormData({ ...formData, zip_code: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Country</label>
              <input
                type="text"
                value={formData.country}
                onChange={(e) => setFormData({ ...formData, country: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={formData.is_default}
                onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
              />
              Default Ship-To Location
            </label>
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
              Active
            </label>
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
            />
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              {location ? 'Update' : 'Create'} Location
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateShipToLocation
