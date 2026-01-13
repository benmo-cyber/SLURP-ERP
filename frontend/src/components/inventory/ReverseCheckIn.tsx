import { useState, useEffect } from 'react'
import { getLots, reverseCheckIn } from '../../api/inventory'
import ConfirmDialog from '../common/ConfirmDialog'
import './ReverseCheckIn.css'

interface Lot {
  id: number
  lot_number: string
  item: {
    name: string
    sku: string
  }
  quantity: number
  quantity_remaining: number
  received_date: string
}

interface ReverseCheckInProps {
  onClose: () => void
  onSuccess: () => void
}

function ReverseCheckIn({ onClose, onSuccess }: ReverseCheckInProps) {
  const [lots, setLots] = useState<Lot[]>([])
  const [selectedLotId, setSelectedLotId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  useEffect(() => {
    loadLots()
  }, [])

  const loadLots = async () => {
    try {
      setLoading(true)
      const data = await getLots()
      // Only show lots that haven't been used (quantity_remaining === quantity)
      setLots(data.filter((lot: Lot) => lot.quantity_remaining === lot.quantity))
    } catch (error) {
      console.error('Failed to load lots:', error)
      alert('Failed to load lots')
    } finally {
      setLoading(false)
    }
  }

  const handleReverse = async () => {
    if (!selectedLotId) {
      alert('Please select a lot to reverse')
      return
    }

    const selectedLot = lots.find(l => l.id === selectedLotId)
    if (!selectedLot) {
      return
    }

    // Show confirmation dialog
    setShowConfirmDialog(true)
  }

  const confirmReverse = async () => {
    if (!selectedLotId) return

    setShowConfirmDialog(false)

    try {
      setSubmitting(true)
      await reverseCheckIn(selectedLotId)
      alert('Check-in reversed successfully')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to reverse check-in:', error)
      console.error('Error response:', error.response?.data)
      console.error('Error status:', error.response?.status)
      const errorMessage = error.response?.data?.error || 
                          error.response?.data?.detail || 
                          error.response?.data?.message ||
                          error.message || 
                          'Failed to reverse check-in'
      alert(`Failed to reverse check-in: ${errorMessage}`)
    } finally {
      setSubmitting(false)
    }
  }

  const cancelReverse = () => {
    setShowConfirmDialog(false)
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content reverse-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Reverse Check-In (Admin Only)</h2>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
          <div className="modal-body">
            <div className="loading">Loading lots...</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content reverse-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Reverse Check-In (Admin Only)</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="modal-body">
          <p className="warning-text">
            Are you sure you want to UNFK? Once UNFK'd you cannot RFK
          </p>

          <div className="form-group">
            <label>Select Lot to Reverse *</label>
            {lots.length === 0 ? (
              <div className="empty-state">No reversible lots found. All lots have been partially or fully used.</div>
            ) : (
              <select
                value={selectedLotId || ''}
                onChange={(e) => setSelectedLotId(parseInt(e.target.value))}
                className="lot-select"
              >
                <option value="">-- Select a lot --</option>
                {lots.map((lot) => (
                  <option key={lot.id} value={lot.id}>
                    {lot.lot_number} - {lot.item.name} ({lot.item.sku}) - {lot.quantity.toLocaleString()} units
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReverse}
              className="btn btn-danger"
              disabled={!selectedLotId || submitting || lots.length === 0}
            >
              {submitting ? 'Reversing...' : 'Reverse Check-In'}
            </button>
          </div>
        </div>
      </div>

      {showConfirmDialog && (
        <ConfirmDialog
          message="Are you sure you want to UNFK? Once UNFK'd you cannot RFK"
          onConfirm={confirmReverse}
          onCancel={cancelReverse}
        />
      )}
    </div>
  )
}

export default ReverseCheckIn

