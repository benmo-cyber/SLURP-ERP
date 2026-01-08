import { useState } from 'react'
import { updateProductionBatch } from '../../api/inventory'
import './CloseBatch.css'

interface CloseBatchProps {
  batch: any
  onClose: () => void
  onSuccess: () => void
}

function CloseBatch({ batch, onClose, onSuccess }: CloseBatchProps) {
  const [formData, setFormData] = useState({
    quantity_actual: batch.quantity_actual || batch.quantity_produced,
    wastes: batch.wastes || 0,
    spills: batch.spills || 0,
    qc_parameters: '',
    qc_actual: '',
    qc_initials: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.qc_parameters || !formData.qc_actual || !formData.qc_initials) {
      alert('Please fill in all QC fields')
      return
    }

    try {
      setSubmitting(true)
      
      await updateProductionBatch(batch.id, {
        quantity_actual: parseFloat(formData.quantity_actual.toString()),
        wastes: parseFloat(formData.wastes.toString()),
        spills: parseFloat(formData.spills.toString()),
        status: 'closed',
        closed_date: new Date().toISOString(),
        qc_parameters: formData.qc_parameters,
        qc_actual: formData.qc_actual,
        qc_initials: formData.qc_initials.toUpperCase(),
      })
      
      alert('Batch closed successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to close batch:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to close batch')
    } finally {
      setSubmitting(false)
    }
  }

  const variance = formData.quantity_actual - batch.quantity_produced

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content close-batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Close Batch: {batch.batch_number}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="close-batch-form">
          <div className="batch-info">
            <div className="info-item">
              <label>Finished Good:</label>
              <span>{batch.finished_good_item.name}</span>
            </div>
            <div className="info-item">
              <label>Quantity to Produce:</label>
              <span>{batch.quantity_produced.toLocaleString()} lbs</span>
            </div>
          </div>

          <div className="form-section">
            <h3>Production Results</h3>
            <div className="form-grid">
              <div className="form-group">
                <label>Quantity Produced (lbs) *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.quantity_actual}
                  onChange={(e) => setFormData({ ...formData, quantity_actual: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label>Variance</label>
                <input
                  type="number"
                  value={variance.toFixed(2)}
                  disabled
                  className={variance >= 0 ? 'positive' : 'negative'}
                />
              </div>

              <div className="form-group">
                <label>Wastes (lbs)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.wastes}
                  onChange={(e) => setFormData({ ...formData, wastes: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Spills (lbs)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.spills}
                  onChange={(e) => setFormData({ ...formData, spills: e.target.value })}
                />
              </div>
            </div>
          </div>

          <div className="form-section">
            <h3>Quality Control</h3>
            <div className="form-grid">
              <div className="form-group full-width">
                <label>QC Parameter *</label>
                <input
                  type="text"
                  value={formData.qc_parameters}
                  onChange={(e) => setFormData({ ...formData, qc_parameters: e.target.value })}
                  required
                  placeholder="e.g., Color, pH, Moisture"
                />
              </div>

              <div className="form-group">
                <label>Actual Result *</label>
                <input
                  type="text"
                  value={formData.qc_actual}
                  onChange={(e) => setFormData({ ...formData, qc_actual: e.target.value })}
                  required
                  placeholder="Enter actual result"
                />
              </div>

              <div className="form-group">
                <label>QC Initials *</label>
                <input
                  type="text"
                  value={formData.qc_initials}
                  onChange={(e) => setFormData({ ...formData, qc_initials: e.target.value.toUpperCase() })}
                  maxLength={3}
                  required
                  placeholder="ABC"
                  style={{ textTransform: 'uppercase' }}
                />
              </div>
            </div>
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Closing...' : 'Close Batch'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CloseBatch






