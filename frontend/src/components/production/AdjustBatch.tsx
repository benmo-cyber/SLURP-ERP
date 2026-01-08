import { useState, useEffect } from 'react'
import { getItems, getFormulas, getLots, getProductionBatch, updateProductionBatch } from '../../api/inventory'
import './AdjustBatch.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
  item_type: string
}

interface Formula {
  id: number
  finished_good: Item
  version: string
  ingredients: FormulaItem[]
}

interface FormulaItem {
  id: number
  item: Item
  percentage: number
}

interface Lot {
  id: number
  lot_number: string
  item: Item
  quantity_remaining: number
  unit_of_measure: string
}

interface BatchInput {
  lot_id: number
  quantity_used: number
}

interface AdjustBatchProps {
  batch: any
  onClose: () => void
  onSuccess: () => void
}

function AdjustBatch({ batch, onClose, onSuccess }: AdjustBatchProps) {
  const [formulas, setFormulas] = useState<Formula[]>([])
  const [allLots, setAllLots] = useState<Lot[]>([])
  const [availableLots, setAvailableLots] = useState<Lot[]>([])
  const [selectedFormula, setSelectedFormula] = useState<Formula | null>(null)
  const [quantity, setQuantity] = useState('')
  const [quantityUnit, setQuantityUnit] = useState<'lbs' | 'kg'>('lbs')
  const [selectedLots, setSelectedLots] = useState<{ [key: number]: number }>({})
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [batchDetails, setBatchDetails] = useState<any>(null)

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (selectedFormula) {
      loadAvailableLots(selectedFormula)
    }
  }, [selectedFormula])

  const loadData = async () => {
    try {
      setLoading(true)
      
      // Load batch details with inputs
      const batchData = await getProductionBatch(batch.id)
      setBatchDetails(batchData)
      
      // Set initial values from batch
      if (batchData.finished_good_item) {
        setQuantity(batchData.quantity_produced.toString())
        setQuantityUnit(batchData.finished_good_item.unit_of_measure === 'kg' ? 'kg' : 'lbs')
      }

      // Load existing inputs
      if (batchData.inputs && batchData.inputs.length > 0) {
        const existingInputs: { [key: number]: number } = {}
        batchData.inputs.forEach((input: any) => {
          existingInputs[input.lot.id] = input.quantity_used
        })
        setSelectedLots(existingInputs)
      }

      const [formulasData, lotsData] = await Promise.all([
        getFormulas(),
        getLots()
      ])
      
      setFormulas(formulasData)
      setAllLots(lotsData.filter((lot: Lot) => lot.quantity_remaining > 0))
      
      // Find and set the formula for this batch
      if (batchData.finished_good_item) {
        const formula = formulasData.find((f: Formula) => f.finished_good.id === batchData.finished_good_item.id)
        setSelectedFormula(formula || null)
      }
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load batch data')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableLots = (formula: Formula | null) => {
    if (!formula) {
      setAvailableLots([])
      return
    }

    // Get required SKUs from formula (match by SKU, not vendor-specific item.id)
    // This allows interchangeability of materials from different vendors
    const requiredSkus = formula.ingredients.map(ing => ing.item.sku)
    
    // Filter lots to only show those matching formula ingredients by SKU
    const available = allLots.filter(lot => 
      requiredSkus.includes(lot.item.sku) && lot.quantity_remaining > 0
    )
    
    setAvailableLots(available)
  }

  const handleLotQuantityChange = (lotId: number, quantity: string) => {
    const qty = parseFloat(quantity) || 0
    if (qty > 0) {
      setSelectedLots({ ...selectedLots, [lotId]: qty })
    } else {
      const newSelected = { ...selectedLots }
      delete newSelected[lotId]
      setSelectedLots(newSelected)
    }
  }

  const removeLot = (lotId: number) => {
    const newSelected = { ...selectedLots }
    delete newSelected[lotId]
    setSelectedLots(newSelected)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!quantity || parseFloat(quantity) <= 0) {
      alert('Please enter a valid quantity to produce')
      return
    }

    if (Object.keys(selectedLots).length === 0) {
      alert('Please select at least one lot')
      return
    }

    try {
      setSubmitting(true)

      // Convert quantity if needed
      let quantityToProduce = parseFloat(quantity)
      if (quantityUnit === 'kg' && batchDetails?.finished_good_item?.unit_of_measure === 'lbs') {
        quantityToProduce = quantityToProduce * 2.2
      } else if (quantityUnit === 'lbs' && batchDetails?.finished_good_item?.unit_of_measure === 'kg') {
        quantityToProduce = quantityToProduce / 2.2
      }

      // Prepare inputs array
      const inputs: BatchInput[] = Object.entries(selectedLots).map(([lotId, qty]) => ({
        lot_id: parseInt(lotId),
        quantity_used: qty
      }))

      await updateProductionBatch(batch.id, {
        quantity_produced: quantityToProduce,
        inputs: inputs
      })

      alert('Batch adjusted successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to adjust batch:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to adjust batch')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content adjust-batch-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Adjust Batch Ticket</h2>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
          <div className="modal-body">
            <div className="loading">Loading batch data...</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content adjust-batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Adjust Batch Ticket - {batch.batch_number}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="adjust-batch-form">
          <div className="form-section">
            <h3>Batch Information</h3>
            <div className="info-display">
              <div className="info-item">
                <label>Finished Good:</label>
                <span>{batchDetails?.finished_good_item?.name || batch.finished_good_item.name}</span>
              </div>
              <div className="info-item">
                <label>Formula Version:</label>
                <span>{selectedFormula?.version || 'N/A'}</span>
              </div>
            </div>
          </div>

          {selectedFormula && (
            <div className="form-section">
              <h3>Formula (Read-Only)</h3>
              <div className="formula-display">
                <table className="formula-table">
                  <thead>
                    <tr>
                      <th>Ingredient</th>
                      <th>Percentage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedFormula.ingredients.map((ingredient) => (
                      <tr key={ingredient.id}>
                        <td>{ingredient.item.name} ({ingredient.item.sku})</td>
                        <td>{ingredient.percentage}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="form-section">
            <h3>Production Quantity</h3>
            <div className="quantity-input-group">
              <input
                type="number"
                step="0.01"
                min="0"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
                placeholder="0.00"
              />
              <select
                value={quantityUnit}
                onChange={(e) => setQuantityUnit(e.target.value as 'lbs' | 'kg')}
              >
                <option value="lbs">lbs</option>
                <option value="kg">kg</option>
              </select>
            </div>
            <small className="form-hint">
              Original: {batch.quantity_produced.toLocaleString()} {batchDetails?.finished_good_item?.unit_of_measure || 'lbs'}
            </small>
          </div>

          <div className="form-section">
            <h3>Select Input Lots</h3>
            {availableLots.length === 0 ? (
              <div className="empty-state">No available lots for this formula</div>
            ) : (
              <div className="lots-selection">
                {availableLots.map((lot) => {
                  const isSelected = selectedLots[lot.id] !== undefined
                  const currentQty = selectedLots[lot.id] || 0
                  
                  return (
                    <div key={lot.id} className={`lot-selection-card ${isSelected ? 'selected' : ''}`}>
                      <div className="lot-info">
                        <div className="lot-header">
                          <span className="lot-number">{lot.lot_number}</span>
                          <span className="item-name">{lot.item.name}</span>
                        </div>
                        <div className="lot-details">
                          <span>Available: {lot.quantity_remaining.toLocaleString()} {lot.unit_of_measure}</span>
                        </div>
                      </div>
                      <div className="lot-input">
                        <label>Quantity to Use:</label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max={lot.quantity_remaining}
                          value={isSelected ? currentQty : ''}
                          onChange={(e) => handleLotQuantityChange(lot.id, e.target.value)}
                          placeholder="0.00"
                        />
                        {isSelected && (
                          <button
                            type="button"
                            onClick={() => removeLot(lot.id)}
                            className="btn-remove-lot"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Adjusting...' : 'Save Adjustments'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AdjustBatch






