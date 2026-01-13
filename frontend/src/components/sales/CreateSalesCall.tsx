import { useState, useEffect } from 'react'
import { createSalesCall, updateSalesCall, getCustomerContacts } from '../../api/customers'
import './CreateSalesCall.css'

interface CreateSalesCallProps {
  customerId: number
  call?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateSalesCall({ customerId, call, onClose, onSuccess }: CreateSalesCallProps) {
  const [contacts, setContacts] = useState<any[]>([])
  const [formData, setFormData] = useState({
    contact: call?.contact || '',
    call_date: call?.call_date ? new Date(call.call_date).toISOString().slice(0, 16) : new Date().toISOString().slice(0, 16),
    call_type: call?.call_type || 'phone',
    subject: call?.subject || '',
    notes: call?.notes || '',
    follow_up_required: call?.follow_up_required || false,
    follow_up_date: call?.follow_up_date ? new Date(call.follow_up_date).toISOString().slice(0, 16) : '',
  })

  useEffect(() => {
    loadContacts()
  }, [customerId])

  const loadContacts = async () => {
    try {
      const data = await getCustomerContacts(customerId)
      setContacts(data)
    } catch (error) {
      console.error('Failed to load contacts:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.notes) {
      alert('Please enter call notes')
      return
    }

    try {
      const submitData: any = {
        customer: customerId,
        call_date: formData.call_date,
        call_type: formData.call_type,
        subject: formData.subject,
        notes: formData.notes,
        follow_up_required: formData.follow_up_required,
      }

      if (formData.contact) {
        submitData.contact = parseInt(formData.contact)
      }

      if (formData.follow_up_required && formData.follow_up_date) {
        submitData.follow_up_date = formData.follow_up_date
      }

      if (call) {
        await updateSalesCall(call.id, submitData)
        alert('Sales call updated successfully!')
      } else {
        await createSalesCall(submitData)
        alert('Sales call logged successfully!')
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to save sales call:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save sales call')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-salescall-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{call ? 'Edit Sales Call' : 'Log Sales Call'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="salescall-form">
          <div className="form-row">
            <div className="form-group">
              <label>Call Date & Time *</label>
              <input
                type="datetime-local"
                value={formData.call_date}
                onChange={(e) => setFormData({ ...formData, call_date: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Call Type *</label>
              <select
                value={formData.call_type}
                onChange={(e) => setFormData({ ...formData, call_type: e.target.value })}
                required
              >
                <option value="phone">Phone Call</option>
                <option value="email">Email</option>
                <option value="meeting">In-Person Meeting</option>
                <option value="video">Video Call</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Contact</label>
            <select
              value={formData.contact}
              onChange={(e) => setFormData({ ...formData, contact: e.target.value })}
            >
              <option value="">Select Contact (Optional)</option>
              {contacts.map((contact) => (
                <option key={contact.id} value={contact.id}>
                  {contact.full_name} {contact.title ? `- ${contact.title}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Subject</label>
            <input
              type="text"
              value={formData.subject}
              onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
              placeholder="Brief subject/topic of the call"
            />
          </div>

          <div className="form-group">
            <label>Notes *</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              required
              rows={6}
              placeholder="Enter call notes, discussion points, outcomes..."
            />
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={formData.follow_up_required}
                onChange={(e) => setFormData({ ...formData, follow_up_required: e.target.checked })}
              />
              Follow-up Required
            </label>
          </div>

          {formData.follow_up_required && (
            <div className="form-group">
              <label>Follow-up Date & Time</label>
              <input
                type="datetime-local"
                value={formData.follow_up_date}
                onChange={(e) => setFormData({ ...formData, follow_up_date: e.target.value })}
              />
            </div>
          )}

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              {call ? 'Update' : 'Log'} Call
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateSalesCall
