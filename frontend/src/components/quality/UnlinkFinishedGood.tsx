import { useState, useEffect } from 'react'
import { getItems, deleteItem } from '../../api/inventory'
import { getFormulas } from '../../api/inventory'
import './UnlinkFinishedGood.css'

interface Item {
  id: number
  sku: string
  name: string
  item_type: string
}

interface UnlinkFinishedGoodProps {
  onClose: () => void
  onSuccess: () => void
}

function UnlinkFinishedGood({ onClose, onSuccess }: UnlinkFinishedGoodProps) {
  const [finishedGoods, setFinishedGoods] = useState<Item[]>([])
  const [formulas, setFormulas] = useState<any[]>([])
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [itemsData, formulasData] = await Promise.all([
        getItems(),
        getFormulas()
      ])
      const finishedGoods = itemsData.filter((item: Item) => item.item_type === 'finished_good')
      setFinishedGoods(finishedGoods)
      setFormulas(formulasData)
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load finished goods')
    } finally {
      setLoading(false)
    }
  }

  const handleUnlink = async () => {
    if (!selectedItemId) {
      alert('Please select a finished good to unlink')
      return
    }

    const selectedItem = finishedGoods.find(item => item.id === selectedItemId)
    if (!selectedItem) return

    // Check if finished good has a formula
    const hasFormula = formulas.some(f => f.finished_good?.id === selectedItemId)
    const formulaWarning = hasFormula ? ' This will also delete the associated formula and FPS.' : ''

    if (!confirm(`Are you sure you want to UNFK this finished good? This action cannot be undone.${formulaWarning}`)) {
      return
    }

    try {
      setSubmitting(true)
      await deleteItem(selectedItemId)
      alert('Finished good unlinked successfully')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to unlink finished good:', error)
      const errorMessage = error.response?.data?.detail || error.response?.data?.message || error.message || 'Failed to unlink finished good'
      alert(`Failed to unlink finished good: ${errorMessage}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content unlink-finished-good-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>UNFK - Unlink Finished Good</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="loading">Loading finished goods...</div>
          ) : (
            <>
              <div className="form-group">
                <label htmlFor="item-select">Select Finished Good to Unlink *</label>
                <select
                  id="item-select"
                  value={selectedItemId || ''}
                  onChange={(e) => setSelectedItemId(e.target.value ? parseInt(e.target.value) : null)}
                  className="item-select"
                >
                  <option value="">Select a finished good...</option>
                  {finishedGoods.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.sku} - {item.name}
                    </option>
                  ))}
                </select>
              </div>

              {selectedItemId && (
                <div className="warning-box">
                  <strong>Warning:</strong> Unlinking a finished good will permanently remove it from the system. 
                  This action cannot be undone. Make sure there are no active lots, purchase orders, sales orders, 
                  or production batches associated with this finished good.
                  {formulas.some(f => f.finished_good?.id === selectedItemId) && (
                    <div style={{ marginTop: '10px', color: '#e74c3c' }}>
                      <strong>⚠️ This finished good has a formula. Deleting it will also delete the formula and FPS.</strong>
                    </div>
                  )}
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
            {submitting ? 'Unlinking...' : 'Unlink Finished Good'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default UnlinkFinishedGood
