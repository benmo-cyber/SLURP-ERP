import { useState } from 'react'
import { createCustomerContact, updateCustomerContact } from '../../api/customers'
import './CreateContact.css'

interface CreateContactProps {
  customerId: number
  contact?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateContact({ customerId, contact, onClose, onSuccess }: CreateContactProps) {
  const [formData, setFormData] = useState({
    first_name: contact?.first_name || '',
    last_name: contact?.last_name || '',
    title: contact?.title || '',
    email: contact?.email || '',
    phone: contact?.phone || '',
    mobile: contact?.mobile || '',
    is_primary: contact?.is_primary || false,
    is_active: contact?.is_active !== undefined ? contact.is_active : true,
    notes: contact?.notes || '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.first_name || !formData.last_name) {
      alert('Please fill in First Name and Last Name')
      return
    }

    try {
      if (contact) {
        await updateCustomerContact(contact.id, { ...formData, customer: customerId })
        alert('Contact updated successfully!')
      } else {
        await createCustomerContact({ ...formData, customer: customerId })
        alert('Contact created successfully!')
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to save contact:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save contact')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-contact-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{contact ? 'Edit Contact' : 'Add Contact'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="contact-form">
          <div className="form-row">
            <div className="form-group">
              <label>First Name *</label>
              <input
                type="text"
                value={formData.first_name}
                onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Last Name *</label>
              <input
                type="text"
                value={formData.last_name}
                onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label>Title/Position</label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Purchasing Manager"
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

            <div className="form-group">
              <label>Mobile</label>
              <input
                type="text"
                value={formData.mobile}
                onChange={(e) => setFormData({ ...formData, mobile: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={formData.is_primary}
                onChange={(e) => setFormData({ ...formData, is_primary: e.target.checked })}
              />
              Primary Contact
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
              {contact ? 'Update' : 'Create'} Contact
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateContact
