import { useState } from 'react'
import { createCustomerContact, updateCustomerContact } from '../../api/customers'
import './CreateContact.css'

function parseEmailsInput(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((e) => e.trim())
    .filter(Boolean)
}

function formatEmailsForInput(emails?: string[]): string {
  return (emails || []).join('\n')
}

interface CreateContactProps {
  customerId: number
  contact?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateContact({ customerId, contact, onClose, onSuccess }: CreateContactProps) {
  const CONTACT_TYPES = [
    { value: 'general', label: 'General' },
    { value: 'billing', label: 'Billing' },
    { value: 'sales', label: 'Sales' },
    { value: 'shipping', label: 'Shipping' },
    { value: 'other', label: 'Other' },
  ]

  const [formData, setFormData] = useState({
    first_name: contact?.first_name || '',
    last_name: contact?.last_name || '',
    title: contact?.title || '',
    contact_type: contact?.contact_type || 'general',
    emailsText: formatEmailsForInput(contact?.emails),
    phone: contact?.phone || '',
    mobile: contact?.mobile || '',
    is_primary: contact?.is_primary || false,
    is_ap_contact: contact?.is_ap_contact || false,
    is_purchasing_contact: contact?.is_purchasing_contact || false,
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
      const emails = parseEmailsInput(formData.emailsText)
      const payload = {
        customer: customerId,
        first_name: formData.first_name,
        last_name: formData.last_name,
        title: formData.title,
        contact_type: formData.contact_type,
        emails,
        phone: formData.phone,
        mobile: formData.mobile,
        is_primary: formData.is_primary,
        is_ap_contact: formData.is_ap_contact,
        is_purchasing_contact: formData.is_purchasing_contact,
        is_active: formData.is_active,
        notes: formData.notes,
      }
      if (contact) {
        await updateCustomerContact(contact.id, payload)
        alert('Contact updated successfully!')
      } else {
        await createCustomerContact(payload)
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

          <div className="form-row">
            <div className="form-group">
              <label>Title/Position</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="e.g., Purchasing Manager"
              />
            </div>
            <div className="form-group">
              <label>Contact type</label>
              <select
                value={formData.contact_type}
                onChange={(e) => setFormData({ ...formData, contact_type: e.target.value })}
              >
                {CONTACT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group" style={{ flex: '1 1 100%', minWidth: '200px' }}>
              <label>Email addresses</label>
              <textarea
                rows={4}
                placeholder="One per line, or separate with commas"
                value={formData.emailsText}
                onChange={(e) => setFormData({ ...formData, emailsText: e.target.value })}
              />
              <small style={{ color: '#666' }}>Multiple addresses allowed (invoices / SO confirmations go to all A/P or purchasing emails).</small>
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
                checked={formData.is_ap_contact}
                onChange={(e) => setFormData({ ...formData, is_ap_contact: e.target.checked })}
              />
              A/P contact (receives invoices when issued)
            </label>
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={formData.is_purchasing_contact}
                onChange={(e) => setFormData({ ...formData, is_purchasing_contact: e.target.checked })}
              />
              Purchasing contact (receives sales order confirmations when issued)
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
