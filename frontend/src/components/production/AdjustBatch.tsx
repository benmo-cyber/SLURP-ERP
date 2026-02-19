import { useState, useEffect } from 'react'
import { getItems, getFormulas, getLots, getProductionBatch, updateProductionBatch } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
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
  vendor_lot_number?: string | null
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
  const [lotInputValues, setLotInputValues] = useState<{ [key: number]: string }>({})
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

  useEffect(() => {
    // When quantityUnit changes, recalculate display values for all selected lots
    if (Object.keys(selectedLots).length > 0 && batchDetails?.inputs) {
      const newInputValues: { [key: number]: string } = {}
      
      batchDetails.inputs.forEach((input: any) => {
        const lot = input.lot
        const storedQty = selectedLots[lot.id]  // This is in lot's native unit
        if (storedQty !== undefined) {
          const lotUnit = lot.item.unit_of_measure
          
          // Convert from lot's native unit to display unit (quantityUnit)
          let displayQty = storedQty
          if (quantityUnit !== lotUnit) {
            if (quantityUnit === 'kg' && lotUnit === 'lbs') {
              displayQty = storedQty / 2.20462
            } else if (quantityUnit === 'lbs' && lotUnit === 'kg') {
              displayQty = storedQty * 2.20462
            }
          }
          
          // Preserve exact integers
          const roundedToInt = Math.round(displayQty)
          const isInteger = Math.abs(displayQty - roundedToInt) <= 0.01
          const finalDisplayQty = isInteger ? roundedToInt : Math.round(displayQty * 100) / 100
          
          newInputValues[lot.id] = finalDisplayQty.toString()
        }
      })
      
      setLotInputValues(newInputValues)
    }
  }, [quantityUnit, selectedLots, batchDetails])

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

      // Load existing inputs - convert from lot's native unit to display unit
      if (batchData.inputs && batchData.inputs.length > 0) {
        const existingInputs: { [key: number]: number } = {}
        const existingInputValues: { [key: number]: string } = {}
        
        batchData.inputs.forEach((input: any) => {
          const lot = input.lot
          const storedQty = input.quantity_used  // This is in lot's native unit
          const lotUnit = lot.item.unit_of_measure
          
          // Convert from lot's native unit to display unit (quantityUnit)
          let displayQty = storedQty
          if (quantityUnit !== lotUnit) {
            if (quantityUnit === 'kg' && lotUnit === 'lbs') {
              displayQty = storedQty / 2.20462
            } else if (quantityUnit === 'lbs' && lotUnit === 'kg') {
              displayQty = storedQty * 2.20462
            }
          }
          
          // Preserve exact integers
          const roundedToInt = Math.round(displayQty)
          const isInteger = Math.abs(displayQty - roundedToInt) <= 0.01
          const finalDisplayQty = isInteger ? roundedToInt : Math.round(displayQty * 100) / 100
          
          // Store in lot's native unit for submission (storedQty)
          existingInputs[lot.id] = storedQty
          // Store display value for input field
          existingInputValues[lot.id] = finalDisplayQty.toString()
        })
        
        setSelectedLots(existingInputs)
        setLotInputValues(existingInputValues)
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

  const convertWeight = (value: number, from: 'lbs' | 'kg', to: 'lbs' | 'kg'): number => {
    if (from === to) return value
    if (from === 'lbs' && to === 'kg') {
      const converted = value / 2.20462
      return Math.round(converted * 100) / 100
    }
    if (from === 'kg' && to === 'lbs') {
      const converted = value * 2.20462
      return Math.round(converted * 100) / 100
    }
    return value
  }

  const handleLotQuantityChange = (lotId: number, quantity: string, lotUnitOfMeasure: string) => {
    // Update the input value state
    const newInputValues = { ...lotInputValues }
    if (quantity === '') {
      delete newInputValues[lotId]
    } else {
      newInputValues[lotId] = quantity
    }
    setLotInputValues(newInputValues)
    
    // Convert and store in lot's native unit
    const newSelectedLots = { ...selectedLots }
    if (quantity === '' || parseFloat(quantity) <= 0 || isNaN(parseFloat(quantity))) {
      delete newSelectedLots[lotId]
    } else {
      const parsedQuantity = parseFloat(quantity)
      
      // User enters quantity in quantityUnit (display unit)
      // Convert to lot's native unit for storage
      if (quantityUnit === lotUnitOfMeasure) {
        // Preserve exact integers
        const roundedToInt = Math.round(parsedQuantity)
        const isInteger = Math.abs(parsedQuantity - roundedToInt) <= 0.01
        newSelectedLots[lotId] = isInteger ? roundedToInt : Math.round(parsedQuantity * 100) / 100
      } else {
        // Need to convert from display unit to lot's native unit
        const quantityInLotUnit = convertWeight(parsedQuantity, quantityUnit, lotUnitOfMeasure as 'lbs' | 'kg')
        newSelectedLots[lotId] = quantityInLotUnit
      }
    }
    setSelectedLots(newSelectedLots)
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

      // Convert quantity if needed and round to 2 decimal places
      let quantityToProduce = parseFloat(quantity)
      if (quantityUnit === 'kg' && batchDetails?.finished_good_item?.unit_of_measure === 'lbs') {
        quantityToProduce = quantityToProduce * 2.20462
      } else if (quantityUnit === 'lbs' && batchDetails?.finished_good_item?.unit_of_measure === 'kg') {
        quantityToProduce = quantityToProduce / 2.20462
      }
      quantityToProduce = Math.round(quantityToProduce * 100) / 100

      // Prepare inputs array - round all quantities to 2 decimal places
      const inputs: BatchInput[] = Object.entries(selectedLots).map(([lotId, qty]) => ({
        lot_id: parseInt(lotId),
        quantity_used: Math.round(qty * 100) / 100
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
              Original: {formatNumber(batch.quantity_produced)} {batchDetails?.finished_good_item?.unit_of_measure || 'lbs'}
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
                  const currentQty = lotInputValues[lot.id] || ''
                  
                  // Calculate max value in display unit
                  const maxInDisplayUnit = quantityUnit === lot.unit_of_measure
                    ? lot.quantity_remaining
                    : (lot.unit_of_measure === 'lbs'
                        ? convertWeight(lot.quantity_remaining, 'lbs', quantityUnit)
                        : convertWeight(lot.quantity_remaining, 'kg', quantityUnit))
                  
                  return (
                    <div key={lot.id} className={`lot-selection-card ${isSelected ? 'selected' : ''}`}>
                      <div className="lot-info">
                        <div className="lot-header">
                          <span className="lot-number">
                            {lot.item.item_type === 'raw_material' && lot.vendor_lot_number 
                              ? `Vendor Lot: ${lot.vendor_lot_number}` 
                              : `Lot: ${lot.lot_number}`}
                          </span>
                          <span className="item-name">{lot.item.name}</span>
                        </div>
                        <div className="lot-details">
                          <span>Available: {formatNumber(lot.quantity_remaining)} {lot.unit_of_measure}</span>
                        </div>
                      </div>
                      <div className="lot-input">
                        <label>Quantity to Use:</label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max={maxInDisplayUnit}
                            value={currentQty}
                            onChange={(e) => handleLotQuantityChange(lot.id, e.target.value, lot.unit_of_measure)}
                            placeholder="0.00"
                            style={{ flex: 1 }}
                          />
                          <span style={{ minWidth: '40px' }}>{quantityUnit}</span>
                        </div>
                        {isSelected && (
                          <button
                            type="button"
                            onClick={() => {
                              const newSelected = { ...selectedLots }
                              const newInputValues = { ...lotInputValues }
                              delete newSelected[lot.id]
                              delete newInputValues[lot.id]
                              setSelectedLots(newSelected)
                              setLotInputValues(newInputValues)
                            }}
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






