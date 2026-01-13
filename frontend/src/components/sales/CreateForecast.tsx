import { useState, useEffect } from 'react'
import { createCustomerForecast, updateCustomerForecast } from '../../api/customers'
import { getItems } from '../../api/inventory'
import './CreateForecast.css'

interface CreateForecastProps {
  customerId: number
  forecast?: any
  onClose: () => void
  onSuccess: () => void
}

function CreateForecast({ customerId, forecast, onClose, onSuccess }: CreateForecastProps) {
  const [items, setItems] = useState<any[]>([])
  const [formData, setFormData] = useState({
    item: forecast?.item || '',
    forecast_period: forecast?.forecast_period || '',
    forecast_quantity: forecast?.forecast_quantity || '',
    unit_of_measure: forecast?.unit_of_measure || 'lbs',
    notes: forecast?.notes || '',
  })

  useEffect(() => {
    loadItems()
  }, [])

  const loadItems = async () => {
    try {
      const data = await getItems()
      // Filter to show only finished goods and distributed items
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

    if (!formData.item || !formData.forecast_period || !formData.forecast_quantity) {
      alert('Please fill in all required fields (Item, Forecast Period, Forecast Quantity)')
      return
    }

    try {
      const submitData = {
        customer: customerId,
        item: parseInt(formData.item),
        forecast_period: formData.forecast_period,
        forecast_quantity: parseFloat(formData.forecast_quantity),
        unit_of_measure: formData.unit_of_measure,
        notes: formData.notes,
      }

      if (forecast) {
        await updateCustomerForecast(forecast.id, submitData)
        alert('Forecast updated successfully!')
      } else {
        await createCustomerForecast(submitData)
        alert('Forecast created successfully!')
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to save forecast:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to save forecast')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-forecast-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{forecast ? 'Edit Forecast' : 'Add Forecast'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="forecast-form">
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
              <label>Forecast Period *</label>
              <input
                type="text"
                value={formData.forecast_period}
                onChange={(e) => setFormData({ ...formData, forecast_period: e.target.value })}
                required
                placeholder="e.g., 2025-Q1, 2025-01, 2025"
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

          <div className="form-group">
            <label>Forecast Quantity *</label>
            <input
              type="number"
              step="0.01"
              value={formData.forecast_quantity}
              onChange={(e) => setFormData({ ...formData, forecast_quantity: e.target.value })}
              required
              min="0"
            />
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
              placeholder="Additional notes about this forecast..."
            />
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              {forecast ? 'Update' : 'Create'} Forecast
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateForecast
