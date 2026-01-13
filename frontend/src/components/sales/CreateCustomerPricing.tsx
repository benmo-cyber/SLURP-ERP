import { useState, useEffect } from 'react'
import { createCustomerPricing, updateCustomerPricing } from '../../api/customers'
import { getItems } from '../../api/inventory'
import './CreateCustomerPricing.css'

interface CreateCustomerPricingProps {
  customerId: number
  pricing?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateCustomerPricing({ customerId, pricing, onClose, onSuccess }: CreateCustomerPricingProps) {
  const [items, setItems] = useState<any[]>([])
  const [formData, setFormData] = useState({
    item: pricing?.item || '',
    unit_price: pricing?.unit_price || '',
    unit_of_measure: pricing?.unit_of_measure || 'lbs',
    effective_date: pricing?.effective_date || new Date().toISOString().split('T')[0],
    expiry_date: pricing?.expiry_date || '',
    is_active: pricing?.is_active !== undefined ? pricing.is_active : true,
    notes: pricing?.notes || '',
  })

  useEffect(() => {
    loadItems()
  }, [])

  const loadItems = async () => {
    try {
      const data = await getItems()
      // Filter to show only finished goods and distributed items for customer pricing
      const filtered = data.filter((item: any) => 
        item.item_type === 'finished_good' || item.item_type === 'distributed_item'
      )
      setItems(filtered)
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.item || !formData.unit_price || !formData.effective_date) {
      alert('Please fill in all required fields (Item, Unit Price, Effective Date)')
      return
    }

    try {
      const submitData: any = {
        customer: customerId,
        item: parseInt(formData.item),
        unit_price: parseFloat(formData.unit_price),
        unit_of_measure: formData.unit_of_measure,
        effective_date: formData.effective_date,
        is_active: formData.is_active,
        notes: formData.notes,
      }

      if (formData.expiry_date) {
        submitData.expiry_date = formData.expiry_date
      }

      if (pricing) {
        await updateCustomerPricing(pricing.id, submitData)
        alert('Customer pricing updated successfully!')
      } else {
        await createCustomerPricing(submitData)
        alert('Customer pricing created successfully!')
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to save customer pricing:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save customer pricing')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-customer-pricing-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{pricing ? 'Edit Customer Pricing' : 'Add Customer Pricing'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="customer-pricing-form">
          <div className="form-group">
            <label>Item *</label>
            <select
              value={formData.item}
              onChange={(e) => setFormData({ ...formData, item: e.target.value })}
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
              <label>Unit Price *</label>
              <input
                type="number"
                step="0.01"
                value={formData.unit_price}
                onChange={(e) => setFormData({ ...formData, unit_price: e.target.value })}
                required
                min="0"
              />
            </div>

            <div className="form-group">
              <label>Unit of Measure *</label>
              <select
                value={formData.unit_of_measure}
                onChange={(e) => setFormData({ ...formData, unit_of_measure: e.target.value })}
                required
              >
                <option value="lbs">Pounds (lbs)</option>
                <option value="kg">Kilograms (kg)</option>
                <option value="ea">Each (ea)</option>
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
              {pricing ? 'Update' : 'Create'} Pricing
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateCustomerPricing
