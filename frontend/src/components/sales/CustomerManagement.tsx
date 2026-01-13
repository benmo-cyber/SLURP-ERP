import { useState, useEffect } from 'react'
import { getCustomers, createCustomer, updateCustomer, deleteCustomer } from '../../api/customers'
import './CustomerManagement.css'

interface Customer {
  id: number
  customer_id: string
  name: string
  contact_name?: string
  email?: string
  phone?: string
  address?: string
  city?: string
  state?: string
  zip_code?: string
  country?: string
  payment_terms?: string
  notes?: string
  is_active: boolean
}

interface CustomerManagementProps {
  onClose: () => void
  onSelect?: (customer: Customer) => void
}

function CustomerManagement({ onClose, onSelect }: CustomerManagementProps) {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null)
  const [formData, setFormData] = useState({
    customer_id: 'AUTO',
    name: '',
    contact_name: '',
    email: '',
    phone: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'USA',
    payment_terms: '',
    notes: '',
    is_active: true,
  })

  useEffect(() => {
    loadCustomers()
  }, [])

  const loadCustomers = async () => {
    try {
      setLoading(true)
      const data = await getCustomers()
      setCustomers(data)
    } catch (error) {
      console.error('Failed to load customers:', error)
      alert('Failed to load customers')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name) {
      alert('Please fill in Customer Name')
      return
    }
    
    // Don't send customer_id for new customers - let backend generate it
    const submitData = { ...formData }
    if (!editingCustomer) {
      delete submitData.customer_id
    }

    try {
      if (editingCustomer) {
        await updateCustomer(editingCustomer.id, submitData)
        alert('Customer updated successfully!')
      } else {
        await createCustomer(submitData)
        alert('Customer created successfully!')
      }
      setShowForm(false)
      setEditingCustomer(null)
      resetForm()
      loadCustomers()
    } catch (error: any) {
      console.error('Failed to save customer:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save customer')
    }
  }

  const handleEdit = (customer: Customer) => {
    setEditingCustomer(customer)
    setFormData({
      customer_id: customer.customer_id,
      name: customer.name,
      contact_name: customer.contact_name || '',
      email: customer.email || '',
      phone: customer.phone || '',
      address: customer.address || '',
      city: customer.city || '',
      state: customer.state || '',
      zip_code: customer.zip_code || '',
      country: customer.country || 'USA',
      payment_terms: customer.payment_terms || '',
      notes: customer.notes || '',
      is_active: customer.is_active,
    })
    setShowForm(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this customer?')) {
      return
    }

    try {
      await deleteCustomer(id)
      alert('Customer deleted successfully!')
      loadCustomers()
    } catch (error: any) {
      console.error('Failed to delete customer:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to delete customer')
    }
  }

  const resetForm = () => {
    setFormData({
      customer_id: 'AUTO',
      name: '',
      contact_name: '',
      email: '',
      phone: '',
      address: '',
      city: '',
      state: '',
      zip_code: '',
      country: 'USA',
      payment_terms: '',
      notes: '',
      is_active: true,
    })
  }

  const handleSelect = (customer: Customer) => {
    if (onSelect) {
      onSelect(customer)
      onClose()
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content customer-management-modal" onClick={(e) => e.stopPropagation()}>
          <div className="loading">Loading customers...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content customer-management-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Customer Management</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        {showForm ? (
          <form onSubmit={handleSubmit} className="customer-form">
            <div className="form-group">
              <label>Customer ID *</label>
              <input
                type="text"
                value={editingCustomer ? formData.customer_id : 'Auto-generated'}
                onChange={(e) => {
                  if (editingCustomer) {
                    setFormData({ ...formData, customer_id: e.target.value })
                  }
                }}
                required
                disabled={!editingCustomer}
                placeholder="Auto-generated (e.g., 001, 002, 003...)"
                style={{ backgroundColor: editingCustomer ? 'white' : '#f5f5f5', cursor: editingCustomer ? 'text' : 'not-allowed' }}
              />
              <small style={{ color: '#666', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                {editingCustomer ? 'Customer ID cannot be changed' : 'Customer ID is automatically generated in sequential order'}
              </small>
            </div>

            <div className="form-group">
              <label>Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
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
              <label>Address</label>
              <textarea
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                rows={2}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>City</label>
                <input
                  type="text"
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
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
                <label>Zip Code</label>
                <input
                  type="text"
                  value={formData.zip_code}
                  onChange={(e) => setFormData({ ...formData, zip_code: e.target.value })}
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
              <label>Payment Terms</label>
              <input
                type="text"
                value={formData.payment_terms}
                onChange={(e) => setFormData({ ...formData, payment_terms: e.target.value })}
                placeholder="e.g., Net 30, Net 15, Due on Receipt"
              />
            </div>

            <div className="form-group">
              <label>Notes</label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={3}
              />
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

            <div className="form-actions">
              <button type="button" onClick={() => { setShowForm(false); setEditingCustomer(null); resetForm() }} className="btn btn-secondary">
                Cancel
              </button>
              <button type="submit" className="btn btn-primary">
                {editingCustomer ? 'Update' : 'Create'} Customer
              </button>
            </div>
          </form>
        ) : (
          <>
            <div className="customer-list-header">
              <button onClick={() => { setShowForm(true); resetForm() }} className="btn btn-primary">
                + Add Customer
              </button>
            </div>

            <div className="customer-list">
              <table className="customer-table">
                <thead>
                  <tr>
                    <th>Customer ID</th>
                    <th>Name</th>
                    <th>Contact</th>
                    <th>Phone</th>
                    <th>City, State</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="no-data">No customers found</td>
                    </tr>
                  ) : (
                    customers.map((customer) => (
                      <tr key={customer.id} className={!customer.is_active ? 'inactive' : ''}>
                        <td>{customer.customer_id}</td>
                        <td>{customer.name}</td>
                        <td>{customer.contact_name || '-'}</td>
                        <td>{customer.phone || '-'}</td>
                        <td>{customer.city ? `${customer.city}, ${customer.state || ''}` : '-'}</td>
                        <td>{customer.is_active ? 'Active' : 'Inactive'}</td>
                        <td>
                          {onSelect && (
                            <button onClick={() => handleSelect(customer)} className="btn btn-sm btn-primary">
                              Select
                            </button>
                          )}
                          <button onClick={() => handleEdit(customer)} className="btn btn-sm btn-secondary">
                            Edit
                          </button>
                          <button onClick={() => handleDelete(customer.id)} className="btn btn-sm btn-danger">
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default CustomerManagement
