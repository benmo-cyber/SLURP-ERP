import { useState, useEffect } from 'react'
import { updateProductionBatch, getFormulas } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './CloseBatch.css'

interface CloseBatchProps {
  batch: any
  onClose: () => void
  onSuccess: () => void
}

interface Formula {
  id: number
  finished_good: {
    id: number
    sku: string
    name: string
  }
  qc_parameter_name?: string
  qc_spec_min?: number
  qc_spec_max?: number
}

function CloseBatch({ batch, onClose, onSuccess }: CloseBatchProps) {
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [formula, setFormula] = useState<Formula | null>(null)
  const [loadingFormula, setLoadingFormula] = useState(true)
  const [formData, setFormData] = useState({
    quantity_actual: batch.quantity_actual || batch.quantity_produced || '',
    wastes: batch.wastes || '',
    spills: batch.spills || '',
    qc_parameters: '',
    qc_actual: '',
    qc_initials: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [qcValidationError, setQcValidationError] = useState<string>('')

  // Get the unit of measure for the finished good (default to lbs)
  const finishedGoodUnit = batch.finished_good_item?.unit_of_measure || 'lbs'

  // Load formula for the finished good
  useEffect(() => {
    const loadFormula = async () => {
      try {
        setLoadingFormula(true)
        const formulas = await getFormulas()
        const batchFormula = formulas.find((f: Formula) => 
          f.finished_good.id === batch.finished_good_item.id
        )
        setFormula(batchFormula || null)
        
        // Pre-fill QC parameter name if formula has it
        if (batchFormula?.qc_parameter_name) {
          setFormData(prev => ({
            ...prev,
            qc_parameters: batchFormula.qc_parameter_name
          }))
        }
      } catch (error) {
        console.error('Failed to load formula:', error)
      } finally {
        setLoadingFormula(false)
      }
    }
    
    if (batch.finished_good_item?.id) {
      loadFormula()
    }
  }, [batch.finished_good_item?.id])

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

  const validateQcResult = (): boolean => {
    if (!formula || !formula.qc_parameter_name) {
      // No QC parameter defined in formula - allow closure
      return true
    }

    if (!formData.qc_actual) {
      setQcValidationError('QC actual result is required')
      return false
    }

    const actualValue = parseFloat(formData.qc_actual)
    if (isNaN(actualValue)) {
      setQcValidationError('QC actual result must be a valid number')
      return false
    }

    // Check if spec range is defined
    if (formula.qc_spec_min !== null && formula.qc_spec_min !== undefined &&
        formula.qc_spec_max !== null && formula.qc_spec_max !== undefined) {
      
      if (actualValue < formula.qc_spec_min || actualValue > formula.qc_spec_max) {
        setQcValidationError(
          `QC result ${actualValue} is out of acceptable range (${formula.qc_spec_min} - ${formula.qc_spec_max}). ` +
          `Please review before closing the batch.`
        )
        return false
      }
    }

    setQcValidationError('')
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.qc_parameters || !formData.qc_actual || !formData.qc_initials) {
      alert('Please fill in all QC fields')
      return
    }

    // Validate QC result against spec range
    if (!validateQcResult()) {
      return
    }

    try {
      setSubmitting(true)
      
      // Convert input values back to original unit (lbs/kg as stored on batch) for backend
      const qtyActual = typeof formData.quantity_actual === 'string' ? (formData.quantity_actual === '' ? 0 : parseFloat(formData.quantity_actual)) : formData.quantity_actual
      const wastesVal = typeof formData.wastes === 'string' ? (formData.wastes === '' ? 0 : parseFloat(formData.wastes)) : formData.wastes
      const spillsVal = typeof formData.spills === 'string' ? (formData.spills === '' ? 0 : parseFloat(formData.spills)) : formData.spills
      
      const quantityActualInLbs = convertFromDisplay(qtyActual || 0, finishedGoodUnit)
      const wastesInLbs = convertFromDisplay(wastesVal || 0, finishedGoodUnit)
      const spillsInLbs = convertFromDisplay(spillsVal || 0, finishedGoodUnit)

      const ticketNative = Number(batch.quantity_produced) || 0
      const tol = 0.05
      if (ticketNative - quantityActualInLbs > tol) {
        const shortfall = ticketNative - quantityActualInLbs
        const explained = wastesInLbs + spillsInLbs
        if (Math.abs(explained - shortfall) > tol) {
          alert(
            `When production is below the batch ticket, wastes + spills must explain the shortfall.\n\n` +
              `Target − produced = ${shortfall.toFixed(2)} ${finishedGoodUnit}\n` +
              `wastes + spills = ${explained.toFixed(2)} ${finishedGoodUnit}`
          )
          setSubmitting(false)
          return
        }
      }
      
      // Variance = produced − target (stored on batch; serializer recalculates on close)
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

  // Variance (produced − batch ticket) in display units
  const qtyActNative =
    formData.quantity_actual === ''
      ? 0
      : typeof formData.quantity_actual === 'string'
        ? parseFloat(formData.quantity_actual) || 0
        : Number(formData.quantity_actual) || 0
  const varianceNative = qtyActNative - (Number(batch.quantity_produced) || 0)
  const varianceInDisplay = convertQuantity(varianceNative, finishedGoodUnit)

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
              <label>Batch ticket (target):</label>
              <span>{formatNumber(convertQuantity(batch.quantity_produced, finishedGoodUnit))} {getDisplayUnit()}</span>
            </div>
          </div>

          <div className="form-section">
            <h3>Production Results</h3>
            <p className="close-batch-section-hint">
              Enter total weight produced — that amount is added to inventory. Variance compares produced to the batch
              ticket. If you are short, split the shortfall between Wastes and Spills to explain it (totals must match).
            </p>
            <div className="form-grid">
              <div className="form-group">
                <label>Quantity produced — total ({getDisplayUnit()}) *</label>
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
                <label>Variance (produced − target)</label>
                <input
                  type="text"
                  readOnly
                  value={
                    varianceInDisplay >= 0
                      ? `+${formatNumber(Math.abs(varianceInDisplay))} ${getDisplayUnit()}`
                      : `−${formatNumber(Math.abs(varianceInDisplay))} ${getDisplayUnit()} short`
                  }
                  disabled
                  className={varianceInDisplay >= 0 ? 'positive' : 'negative'}
                />
              </div>

              <div className="form-group">
                <label>Wastes — explain shortfall ({getDisplayUnit()})</label>
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
                <label>Spills — explain shortfall ({getDisplayUnit()})</label>
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
            {loadingFormula ? (
              <div>Loading QC specifications...</div>
            ) : formula && formula.qc_parameter_name ? (
              <div className="qc-info-banner" style={{ 
                padding: '0.75rem', 
                marginBottom: '1rem', 
                backgroundColor: '#e0f2fe', 
                borderRadius: '6px',
                border: '1px solid #0284c7'
              }}>
                <strong>Required QC Parameter:</strong> {formula.qc_parameter_name}
                {formula.qc_spec_min !== null && formula.qc_spec_min !== undefined &&
                 formula.qc_spec_max !== null && formula.qc_spec_max !== undefined && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <strong>Acceptable Range:</strong> {formula.qc_spec_min} - {formula.qc_spec_max}
                  </div>
                )}
              </div>
            ) : (
              <div className="qc-info-banner" style={{ 
                padding: '0.75rem', 
                marginBottom: '1rem', 
                backgroundColor: '#fef3c7', 
                borderRadius: '6px',
                border: '1px solid #f59e0b'
              }}>
                <strong>Note:</strong> No QC parameter defined in formula. You can still enter QC data manually.
              </div>
            )}
            <div className="form-grid">
              <div className="form-group full-width">
                <label>QC Parameter *</label>
                <input
                  type="text"
                  value={formData.qc_parameters}
                  onChange={(e) => {
                    setFormData({ ...formData, qc_parameters: e.target.value })
                    setQcValidationError('')
                  }}
                  required
                  placeholder={formula?.qc_parameter_name || "e.g., norbixin, betanin, absorbance"}
                  disabled={!!formula?.qc_parameter_name}
                  style={formula?.qc_parameter_name ? { backgroundColor: '#f3f4f6', cursor: 'not-allowed' } : {}}
                />
              </div>

              <div className="form-group">
                <label>Actual Result *</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.qc_actual}
                  onChange={(e) => {
                    setFormData({ ...formData, qc_actual: e.target.value })
                    setQcValidationError('')
                  }}
                  required
                  placeholder="Enter actual result"
                  className={qcValidationError ? 'error' : ''}
                />
                {qcValidationError && (
                  <div style={{ color: '#dc2626', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                    {qcValidationError}
                  </div>
                )}
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






