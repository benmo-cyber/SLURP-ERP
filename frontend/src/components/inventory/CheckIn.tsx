import { useState, useEffect } from 'react'
import { getItems, createLot, getItemPackSizes } from '../../api/inventory'
import { useBackdatedEntry } from '../../context/BackdatedEntryContext'
import './CheckIn.css'

interface ItemPackSize {
  id: number
  pack_size: number
  pack_size_unit: string
  description?: string
  is_default: boolean
  is_active: boolean
  pack_size_display?: string
}

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
  pack_sizes?: ItemPackSize[]
  default_pack_size?: ItemPackSize
}

function CheckIn() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [formData, setFormData] = useState({
    item_id: '',
    quantity: '',
    received_date: new Date().toISOString().split('T')[0],
    expiration_date: '',
    notes: '',
    pack_size_id: '',
  })
  const [availablePackSizes, setAvailablePackSizes] = useState<ItemPackSize[]>([])

  useEffect(() => {
    loadItems()
  }, [])

  const loadItems = async () => {
    try {
      setLoading(true)
      const data = await getItems()
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
      alert('Failed to load items. Make sure the backend server is running.')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.item_id || !formData.quantity) {
      alert('Please fill in all required fields')
      return
    }

    try {
      setSubmitting(true)
      const checkInData: any = {
        item_id: parseInt(formData.item_id),
        quantity: parseFloat(formData.quantity),
        received_date: formData.received_date,
        expiration_date: formData.expiration_date || null,
        notes: formData.notes || null,
      }
      if (formData.pack_size_id) {
        checkInData.pack_size_id = parseInt(formData.pack_size_id)
      }
      
      await createLot(checkInData)
      
      // Reset form
      setFormData({
        item_id: '',
        quantity: '',
        received_date: new Date().toISOString().split('T')[0],
        expiration_date: '',
        notes: '',
        pack_size_id: '',
      })
      
      alert('Material checked in successfully!')
    } catch (error: any) {
      console.error('Failed to check in material:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to check in material')
    } finally {
      setSubmitting(false)
    }
  }

  const selectedItem = items.find(item => item.id === parseInt(formData.item_id))

  useEffect(() => {
    const loadPackSizes = async () => {
      if (formData.item_id) {
        try {
          const data = await getItemPackSizes(parseInt(formData.item_id))
          setAvailablePackSizes(data.filter(ps => ps.is_active))
          // Set default pack size if available
          const defaultPackSize = data.find(ps => ps.is_default && ps.is_active)
          if (defaultPackSize) {
            setFormData(prev => ({ ...prev, pack_size_id: defaultPackSize.id.toString() }))
          } else if (data.length > 0) {
            setFormData(prev => ({ ...prev, pack_size_id: data[0].id.toString() }))
          } else {
            setFormData(prev => ({ ...prev, pack_size_id: '' }))
          }
        } catch (error) {
          console.error('Failed to load pack sizes:', error)
          setAvailablePackSizes([])
        }
      } else {
        setAvailablePackSizes([])
        setFormData(prev => ({ ...prev, pack_size_id: '' }))
      }
    }
    loadPackSizes()
  }, [formData.item_id])

  if (loading) {
    return <div className="loading">Loading items...</div>
  }

  return (
    <div className="checkin-container">
      <div className="checkin-header">
        <h2>Check In Materials</h2>
        <p>Record inbound materials to add them to inventory</p>
      </div>

      <form onSubmit={handleSubmit} className="checkin-form">
        <div className="form-group">
          <label htmlFor="item_id">Item *</label>
          <select
            id="item_id"
            value={formData.item_id}
            onChange={(e) => setFormData({ ...formData, item_id: e.target.value })}
            required
          >
            <option value="">Select an item...</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.sku} - {item.name} ({item.unit_of_measure})
              </option>
            ))}
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="quantity">Quantity *</label>
            <input
              type="number"
              id="quantity"
              step="0.01"
              min="0"
              value={formData.quantity}
              onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
              required
            />
            {selectedItem && (
              <span className="unit-hint">in {selectedItem.unit_of_measure}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="received_date">Received Date *</label>
            <input
              type="date"
              id="received_date"
              value={formData.received_date}
              onChange={(e) => setFormData({ ...formData, received_date: e.target.value })}
              max={maxDateForEntry}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="expiration_date">Expiration Date (Optional)</label>
            <input
              type="date"
              id="expiration_date"
              value={formData.expiration_date}
              onChange={(e) => setFormData({ ...formData, expiration_date: e.target.value })}
            />
          </div>

          {availablePackSizes.length > 0 && (
            <div className="form-group">
              <label htmlFor="pack_size_id">Pack Size (Optional)</label>
              <select
                id="pack_size_id"
                value={formData.pack_size_id}
                onChange={(e) => setFormData({ ...formData, pack_size_id: e.target.value })}
              >
                <option value="">Select pack size...</option>
                {availablePackSizes.map((ps) => (
                  <option key={ps.id} value={ps.id}>
                    {ps.pack_size} {ps.pack_size_unit} {ps.description ? `- ${ps.description}` : ''} {ps.is_default ? '(Default)' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="notes">Notes (Optional)</label>
          <textarea
            id="notes"
            rows={4}
            value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            placeholder="Any additional notes about this check-in..."
          />
        </div>

        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Checking In...' : 'Check In'}
          </button>
          <button
            type="button"
            onClick={() => setFormData({
              item_id: '',
              quantity: '',
              received_date: new Date().toISOString().split('T')[0],
              expiration_date: '',
              notes: '',
            })}
            className="btn btn-secondary"
            disabled={submitting}
          >
            Clear
          </button>
        </div>
      </form>
    </div>
  )
}

export default CheckIn

