import { useState, useEffect } from 'react'
import { getItems, createVendorPricing } from '../../api/finance'
import './CreatePricing.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
}

interface CreateVendorPricingProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateVendorPricing({ onClose, onSuccess }: CreateVendorPricingProps) {
  const [items, setItems] = useState<Item[]>([])
  const [formData, setFormData] = useState({
    item_id: '',
    vendor_name: '',
    vendor_item_number: '',
    unit_price: '',
    unit_of_measure: 'lbs',
    effective_date: new Date().toISOString().split('T')[0],
    expiry_date: '',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadItems()
  }, [])

  const loadItems = async () => {
    try {
      const data = await getItems()
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.item_id || !formData.vendor_name || !formData.unit_price) {
      alert('Please fill in all required fields')
      return
    }

    try {
      setSubmitting(true)
      
      await createVendorPricing({
        item_id: parseInt(formData.item_id),
        vendor_name: formData.vendor_name,
        vendor_item_number: formData.vendor_item_number || null,
        unit_price: parseFloat(formData.unit_price),
        unit_of_measure: formData.unit_of_measure,
        effective_date: formData.effective_date,
        expiry_date: formData.expiry_date || null,
        is_active: true,
      })
      
      alert('Vendor pricing created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create vendor pricing:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create vendor pricing')
    } finally {
      setSubmitting(false)
    }
  }

  const selectedItem = items.find(item => item.id === parseInt(formData.item_id))

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content pricing-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add Vendor Pricing</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="pricing-form">
          <div className="form-group">
            <label>Item *</label>
            <select
              value={formData.item_id}
              onChange={(e) => {
                setFormData({ ...formData, item_id: e.target.value })
                const item = items.find(i => i.id === parseInt(e.target.value))
                if (item) {
                  setFormData(prev => ({ ...prev, unit_of_measure: item.unit_of_measure }))
                }
              }}
              required
            >
              <option value="">Select Item</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.sku} - {item.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Vendor Name *</label>
              <input
                type="text"
                value={formData.vendor_name}
                onChange={(e) => setFormData({ ...formData, vendor_name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Vendor Item Number</label>
              <input
                type="text"
                value={formData.vendor_item_number}
                onChange={(e) => setFormData({ ...formData, vendor_item_number: e.target.value })}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Unit Price *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.unit_price}
                onChange={(e) => setFormData({ ...formData, unit_price: e.target.value })}
                required
                placeholder="0.00"
              />
            </div>
            <div className="form-group">
              <label>Unit of Measure *</label>
              <select
                value={formData.unit_of_measure}
                onChange={(e) => setFormData({ ...formData, unit_of_measure: e.target.value })}
                required
              >
                <option value="lbs">lbs</option>
                <option value="kg">kg</option>
                <option value="ea">ea</option>
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Effective Date *</label>
              <input
                type="date"
                value={formData.effective_date}
                onChange={(e) => setFormData({ ...formData, effective_date: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Expiry Date</label>
              <input
                type="date"
                value={formData.expiry_date}
                onChange={(e) => setFormData({ ...formData, expiry_date: e.target.value })}
              />
            </div>
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Pricing'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateVendorPricing






