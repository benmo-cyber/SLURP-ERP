import { useState, useEffect } from 'react'
import { getItems, deleteItem } from '../../api/inventory'
import './UnlinkItem.css'

interface Item {
  id: number
  sku: string
  name: string
  vendor?: string
}

interface UnlinkItemProps {
  onClose: () => void
  onSuccess: () => void
}

function UnlinkItem({ onClose, onSuccess }: UnlinkItemProps) {
  const [items, setItems] = useState<Item[]>([])
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

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
      alert('Failed to load items')
    } finally {
      setLoading(false)
    }
  }

  const handleUnlink = async () => {
    if (!selectedItemId) {
      alert('Please select an item to unlink')
      return
    }

    if (!confirm('Are you sure you want to unlink this item? This action cannot be undone.')) {
      return
    }

    try {
      setSubmitting(true)
      await deleteItem(selectedItemId)
      alert('Item unlinked successfully')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to unlink item:', error)
      const errorMessage = error.response?.data?.detail || error.response?.data?.message || error.message || 'Failed to unlink item'
      alert(`Failed to unlink item: ${errorMessage}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content unlink-item-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Unlink item</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="loading">Loading items...</div>
          ) : (
            <>
              <div className="form-group">
                <label htmlFor="item-select">Select Item to Unlink *</label>
                <select
                  id="item-select"
                  value={selectedItemId || ''}
                  onChange={(e) => setSelectedItemId(e.target.value ? parseInt(e.target.value) : null)}
                  className="item-select"
                >
                  <option value="">Select an item...</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.sku} - {item.name} {item.vendor ? `(${item.vendor})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {selectedItemId && (
                <div className="warning-box">
                  <strong>Warning:</strong> Unlinking an item will permanently remove it from the system. 
                  This action cannot be undone. Make sure there are no active lots, purchase orders, or sales orders 
                  associated with this item.
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button onClick={onClose} className="btn btn-secondary" disabled={submitting}>
            Cancel
          </button>
          <button 
            onClick={handleUnlink} 
            className="btn btn-danger" 
            disabled={!selectedItemId || submitting}
          >
            {submitting ? 'Unlinking...' : 'Unlink Item'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default UnlinkItem


