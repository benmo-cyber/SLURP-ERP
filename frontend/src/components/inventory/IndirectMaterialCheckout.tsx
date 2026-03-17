import { useState, useEffect } from 'react'
import { getLots } from '../../api/inventory'
import { api } from '../../api/client'
import './IndirectMaterialCheckout.css'

interface Lot {
  id: number
  lot_number: string
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
  }
  quantity_remaining: number
  status: string
}

function IndirectMaterialCheckout({ onClose, onSuccess }: { onClose: () => void; onSuccess?: () => void }) {
  const [lots, setLots] = useState<Lot[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedLotId, setSelectedLotId] = useState<number | null>(null)
  const [quantity, setQuantity] = useState('')
  const [notes, setNotes] = useState('')
  const [referenceNumber, setReferenceNumber] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadLots()
  }, [])

  const loadLots = async () => {
    try {
      setLoading(true)
      const allLots = await getLots()
      const indirectMaterialLots = allLots.filter((lot: Lot) => 
        lot.item.item_type === 'indirect_material' && 
        lot.quantity_remaining > 0 &&
        (!lot.status || lot.status === 'accepted')
      )
      setLots(indirectMaterialLots)
    } catch (error) {
      console.error('Failed to load lots:', error)
      alert('Failed to load indirect materials')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!selectedLotId || !quantity || parseFloat(quantity) <= 0) {
      alert('Please select a lot and enter a valid quantity')
      return
    }

    const selectedLot = lots.find(l => l.id === selectedLotId)
    if (!selectedLot) {
      alert('Selected lot not found')
      return
    }

    const qty = parseFloat(quantity)
    if (qty > selectedLot.quantity_remaining) {
      alert(`Cannot exceed available quantity: ${selectedLot.quantity_remaining} ${selectedLot.item.unit_of_measure}`)
      return
    }

    try {
      setSubmitting(true)
      
      await api.post(
        `/lots/${selectedLotId}/checkout_indirect_material/`,
        {
          quantity: qty,
          notes: notes || undefined,
          reference_number: referenceNumber || undefined
        }
      )

      alert('Indirect material checked out successfully!')
      
      // Reset form
      setSelectedLotId(null)
      setQuantity('')
      setNotes('')
      setReferenceNumber('')
      
      // Reload lots
      await loadLots()
      
      if (onSuccess) {
        onSuccess()
      }
    } catch (error: any) {
      console.error('Failed to checkout indirect material:', error)
      const errorMessage = error.response?.data?.error || error.response?.data?.detail || 'Failed to checkout indirect material'
      alert(errorMessage)
    } finally {
      setSubmitting(false)
    }
  }

  const selectedLot = selectedLotId ? lots.find(l => l.id === selectedLotId) : null

  return (
    <div className="indirect-material-checkout-modal">
      <div className="indirect-material-checkout-content">
        <div className="indirect-material-checkout-header">
          <h2>Checkout Indirect Material</h2>
          <button type="button" onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Select Indirect Material *</label>
            {loading ? (
              <div>Loading...</div>
            ) : lots.length === 0 ? (
              <div className="info-message">
                No indirect materials available in inventory.
              </div>
            ) : (
              <select
                value={selectedLotId || ''}
                onChange={(e) => setSelectedLotId(e.target.value ? parseInt(e.target.value) : null)}
                required
              >
                <option value="">-- Select --</option>
                {lots.map((lot) => (
                  <option key={lot.id} value={lot.id}>
                    {lot.item.name} ({lot.item.sku}) - Lot: {lot.lot_number} - Available: {lot.quantity_remaining} {lot.item.unit_of_measure}
                  </option>
                ))}
              </select>
            )}
          </div>

          {selectedLot && (
            <>
              <div className="form-group">
                <label>Quantity *</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max={selectedLot.quantity_remaining}
                    value={quantity}
                    onChange={(e) => {
                      const val = e.target.value
                      if (val === '' || (!isNaN(parseFloat(val)) && parseFloat(val) >= 0)) {
                        setQuantity(val)
                      }
                    }}
                    required
                    style={{ flex: 1 }}
                  />
                  <span>{selectedLot.item.unit_of_measure}</span>
                </div>
                <small className="form-hint">
                  Available: {selectedLot.quantity_remaining} {selectedLot.item.unit_of_measure}
                </small>
              </div>

              <div className="form-group">
                <label>Reference Number (Optional)</label>
                <input
                  type="text"
                  value={referenceNumber}
                  onChange={(e) => setReferenceNumber(e.target.value)}
                  placeholder="e.g., Shipping label, Internal reference"
                />
              </div>

              <div className="form-group">
                <label>Notes (Optional)</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Additional notes about this checkout"
                  rows={3}
                />
              </div>
            </>
          )}

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-primary" 
              disabled={submitting || !selectedLotId || !quantity}
            >
              {submitting ? 'Checking Out...' : 'Checkout'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default IndirectMaterialCheckout
