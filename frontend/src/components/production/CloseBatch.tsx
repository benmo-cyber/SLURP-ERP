import { useState } from 'react'
import { updateProductionBatch } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './CloseBatch.css'

interface CloseBatchProps {
  batch: any
  onClose: () => void
  onSuccess: () => void
}

function CloseBatch({ batch, onClose, onSuccess }: CloseBatchProps) {
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [formData, setFormData] = useState({
    quantity_actual: batch.quantity_actual || batch.quantity_produced || '',
    wastes: batch.wastes || '',
    spills: batch.spills || '',
    qc_parameters: '',
    qc_actual: '',
    qc_initials: '',
  })
  const [submitting, setSubmitting] = useState(false)

  // Get the unit of measure for the finished good (default to lbs)
  const finishedGoodUnit = batch.finished_good_item?.unit_of_measure || 'lbs'

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, fromUnit: string = finishedGoodUnit) => {
    if (fromUnit === 'ea') return quantity
    if (unitDisplay === 'kg' && fromUnit === 'lbs') {
      return quantity * 0.453592
    } else if (unitDisplay === 'lbs' && fromUnit === 'kg') {
      return quantity * 2.20462
    }
    return quantity
  }

  // Convert from display unit back to original unit
  const convertFromDisplay = (quantity: number, toUnit: string = finishedGoodUnit) => {
    if (toUnit === 'ea') return quantity
    if (unitDisplay === 'kg' && toUnit === 'lbs') {
      return quantity / 0.453592
    } else if (unitDisplay === 'lbs' && toUnit === 'kg') {
      return quantity / 2.20462
    }
    return quantity
  }

  const getDisplayUnit = () => {
    if (finishedGoodUnit === 'ea') return 'ea'
    return unitDisplay
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.qc_parameters || !formData.qc_actual || !formData.qc_initials) {
      alert('Please fill in all QC fields')
      return
    }

    try {
      setSubmitting(true)
      
      // Convert input values back to original unit (lbs) for backend
      const qtyActual = typeof formData.quantity_actual === 'string' ? (formData.quantity_actual === '' ? 0 : parseFloat(formData.quantity_actual)) : formData.quantity_actual
      const wastesVal = typeof formData.wastes === 'string' ? (formData.wastes === '' ? 0 : parseFloat(formData.wastes)) : formData.wastes
      const spillsVal = typeof formData.spills === 'string' ? (formData.spills === '' ? 0 : parseFloat(formData.spills)) : formData.spills
      
      const quantityActualInLbs = convertFromDisplay(qtyActual || 0, finishedGoodUnit)
      const wastesInLbs = convertFromDisplay(wastesVal || 0, finishedGoodUnit)
      const spillsInLbs = convertFromDisplay(spillsVal || 0, finishedGoodUnit)
      
      // Calculate variance (both should be in same unit)
      const variance = quantityActualInLbs - batch.quantity_produced
      
      // Store QC info in notes
      const qcNotes = `QC Parameters: ${formData.qc_parameters}\nQC Actual: ${formData.qc_actual}\nQC Initials: ${formData.qc_initials.toUpperCase()}`
      const existingNotes = batch.notes ? `${batch.notes}\n\n` : ''
      const notes = `${existingNotes}${qcNotes}`
      
      await updateProductionBatch(batch.id, {
        quantity_actual: quantityActualInLbs,
        wastes: wastesInLbs,
        spills: spillsInLbs,
        variance: variance,
        status: 'closed',
        closed_date: new Date().toISOString(),
        notes: notes,
      })
      
      alert('Batch closed successfully! A new lot has been created and added to inventory. Please refresh the Inventory page to see it.')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to close batch:', error)
      console.error('Error response:', error.response)
      console.error('Error data:', error.response?.data)
      
      // Try to get detailed error message
      let errorMessage = 'Failed to close batch'
      if (error.response?.data) {
        if (error.response.data.detail) {
          errorMessage = error.response.data.detail
        } else if (error.response.data.error) {
          errorMessage = error.response.data.error
        } else if (typeof error.response.data === 'string') {
          errorMessage = error.response.data
        } else if (error.response.data.non_field_errors) {
          errorMessage = error.response.data.non_field_errors.join(', ')
        } else {
          // Try to format validation errors
          const errorParts: string[] = []
          for (const [field, messages] of Object.entries(error.response.data)) {
            if (Array.isArray(messages)) {
              errorParts.push(`${field}: ${messages.join(', ')}`)
            } else if (typeof messages === 'string') {
              errorParts.push(`${field}: ${messages}`)
            } else {
              errorParts.push(`${field}: ${JSON.stringify(messages)}`)
            }
          }
          if (errorParts.length > 0) {
            errorMessage = errorParts.join('\n')
          }
        }
      } else if (error.message) {
        errorMessage = error.message
      }
      
      alert(errorMessage)
    } finally {
      setSubmitting(false)
    }
  }

  // Calculate variance in display units for display
  const varianceInDisplay = convertQuantity(parseFloat(formData.quantity_actual.toString()) || 0, finishedGoodUnit) - convertQuantity(batch.quantity_produced, finishedGoodUnit)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content close-batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Close Batch: {batch.batch_number}</h2>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <div className="unit-toggle">
              <label>Display Units:</label>
              <button
                type="button"
                className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
                onClick={() => setUnitDisplay('lbs')}
              >
                lbs
              </button>
              <button
                type="button"
                className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
                onClick={() => setUnitDisplay('kg')}
              >
                kg
              </button>
            </div>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="close-batch-form">
          <div className="batch-info">
            <div className="info-item">
              <label>Finished Good:</label>
              <span>{batch.finished_good_item.name}</span>
            </div>
            <div className="info-item">
              <label>Quantity to Produce:</label>
              <span>{formatNumber(convertQuantity(batch.quantity_produced, finishedGoodUnit))} {getDisplayUnit()}</span>
            </div>
          </div>

          <div className="form-section">
            <h3>Production Results</h3>
            <div className="form-grid">
              <div className="form-group">
                <label>Quantity Produced ({getDisplayUnit()}) *</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.quantity_actual === '' ? '' : convertQuantity(typeof formData.quantity_actual === 'string' ? parseFloat(formData.quantity_actual) || 0 : formData.quantity_actual, finishedGoodUnit)}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '') {
                      setFormData({ ...formData, quantity_actual: '' })
                    } else {
                      const displayValue = parseFloat(val) || 0
                      const originalValue = convertFromDisplay(displayValue, finishedGoodUnit)
                      setFormData({ ...formData, quantity_actual: originalValue })
                    }
                  }}
                  required
                />
              </div>

              <div className="form-group">
                <label>Variance</label>
                <input
                  type="number"
                  value={formatNumber(varianceInDisplay)}
                  disabled
                  className={varianceInDisplay >= 0 ? 'positive' : 'negative'}
                />
              </div>

              <div className="form-group">
                <label>Wastes ({getDisplayUnit()})</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.wastes === '' ? '' : convertQuantity(typeof formData.wastes === 'string' ? parseFloat(formData.wastes) || 0 : formData.wastes, finishedGoodUnit)}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '') {
                      setFormData({ ...formData, wastes: '' })
                    } else {
                      const displayValue = parseFloat(val) || 0
                      const originalValue = convertFromDisplay(displayValue, finishedGoodUnit)
                      setFormData({ ...formData, wastes: originalValue })
                    }
                  }}
                />
              </div>

              <div className="form-group">
                <label>Spills ({getDisplayUnit()})</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.spills === '' ? '' : convertQuantity(typeof formData.spills === 'string' ? parseFloat(formData.spills) || 0 : formData.spills, finishedGoodUnit)}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '') {
                      setFormData({ ...formData, spills: '' })
                    } else {
                      const displayValue = parseFloat(val) || 0
                      const originalValue = convertFromDisplay(displayValue, finishedGoodUnit)
                      setFormData({ ...formData, spills: originalValue })
                    }
                  }}
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






