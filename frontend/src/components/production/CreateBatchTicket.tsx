import { useState, useEffect } from 'react'
import { getItems, getFormulas, getLots, createProductionBatch } from '../../api/inventory'
import './CreateBatchTicket.css'

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

interface CreateBatchTicketProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateBatchTicket({ onClose, onSuccess }: CreateBatchTicketProps) {
  const [finishedGoods, setFinishedGoods] = useState<Item[]>([])
  const [formulas, setFormulas] = useState<Formula[]>([])
  const [allLots, setAllLots] = useState<Lot[]>([])
  const [availableLots, setAvailableLots] = useState<Lot[]>([])
  const [selectedFinishedGood, setSelectedFinishedGood] = useState<Item | null>(null)
  const [selectedFormula, setSelectedFormula] = useState<Formula | null>(null)
  const [quantity, setQuantity] = useState('')
  const [quantityUnit, setQuantityUnit] = useState<'lbs' | 'kg'>('lbs')
  const [selectedLots, setSelectedLots] = useState<{ [key: number]: number }>({})
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (selectedFinishedGood) {
      const formula = formulas.find(f => f.finished_good.id === selectedFinishedGood.id)
      setSelectedFormula(formula || null)
    } else {
      setSelectedFormula(null)
      setSelectedLots({})
    }
  }, [selectedFinishedGood, formulas])

  useEffect(() => {
    if (selectedFormula) {
      loadAvailableLots(selectedFormula)
    } else {
      setAvailableLots([])
    }
  }, [selectedFormula])

  const loadData = async () => {
    try {
      setLoading(true)
      const [itemsData, formulasData, lotsData] = await Promise.all([
        getItems(),
        getFormulas(),
        getLots()
      ])
      
      const finishedGoods = itemsData.filter((item: Item) => item.item_type === 'finished_good')
      setFinishedGoods(finishedGoods)
      setFormulas(formulasData)
      setAllLots(lotsData.filter((lot: Lot) => lot.quantity_remaining > 0))
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableLots = (formula: Formula | null) => {
    if (!formula) {
      setAvailableLots([])
      return
    }

    // Filter lots to only show those that match formula ingredients by SKU (not vendor-specific item.id)
    // This allows interchangeability of materials from different vendors
    const ingredientSkus = formula.ingredients.map(ing => ing.item.sku)
    const filteredLots = allLots.filter((lot: Lot) => 
      ingredientSkus.includes(lot.item.sku) && lot.quantity_remaining > 0
    )
    setAvailableLots(filteredLots)
  }

  const convertWeight = (value: number, from: 'lbs' | 'kg', to: 'lbs' | 'kg'): number => {
    if (from === to) return value
    if (from === 'lbs' && to === 'kg') return value / 2.2
    if (from === 'kg' && to === 'lbs') return value * 2.2
    return value
  }

  const handleLotQuantityChange = (lotId: number, quantity: string) => {
    const newSelectedLots = { ...selectedLots }
    if (quantity === '' || parseFloat(quantity) <= 0) {
      delete newSelectedLots[lotId]
    } else {
      newSelectedLots[lotId] = parseFloat(quantity)
    }
    setSelectedLots(newSelectedLots)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!selectedFinishedGood || !selectedFormula || !quantity) {
      alert('Please fill in all required fields')
      return
    }

    if (Object.keys(selectedLots).length === 0) {
      alert('Please select at least one lot')
      return
    }

    // Validate that selected lots match formula ingredients by SKU (not vendor-specific item.id)
    // This allows interchangeability of materials from different vendors
    const ingredientSkus = selectedFormula.ingredients.map(ing => ing.item.sku)
    const selectedLotSkus = Object.keys(selectedLots).map(lotId => {
      const lot = availableLots.find(l => l.id === parseInt(lotId))
      return lot?.item.sku
    })

    const allMatch = selectedLotSkus.every(sku => ingredientSkus.includes(sku!))
    if (!allMatch) {
      alert('Selected lots must match formula ingredients')
      return
    }

    try {
      setSubmitting(true)
      
      const quantityInLbs = quantityUnit === 'kg' 
        ? convertWeight(parseFloat(quantity), 'kg', 'lbs')
        : parseFloat(quantity)

      await createProductionBatch({
        finished_good_item_id: selectedFinishedGood.id,
        quantity_produced: quantityInLbs,
        production_date: new Date().toISOString().split('T')[0],
        status: 'in_progress',
        inputs: Object.keys(selectedLots).map(lotId => ({
          lot_id: parseInt(lotId),
          quantity_used: selectedLots[parseInt(lotId)]
        }))
      })
      
      alert('Batch ticket created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create batch ticket:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create batch ticket')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay">
        <div className="modal-content">
          <div className="loading">Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Batch Ticket</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="batch-form">
          <div className="form-group">
            <label>Finished Good *</label>
            <select
              value={selectedFinishedGood?.id || ''}
              onChange={(e) => {
                const item = finishedGoods.find(i => i.id === parseInt(e.target.value))
                setSelectedFinishedGood(item || null)
              }}
              required
            >
              <option value="">Select Finished Good</option>
              {finishedGoods.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.sku} - {item.name}
                </option>
              ))}
            </select>
          </div>

          {selectedFormula && (
            <>
              <div className="formula-section">
                <label className="section-label">Formula (Auto-populated, Read-only)</label>
                <div className="formula-display">
                  <div className="formula-header">
                    <span className="formula-version">Version: {selectedFormula.version}</span>
                  </div>
                  <div className="ingredients-list">
                    {selectedFormula.ingredients.map((ingredient) => (
                      <div key={ingredient.id} className="ingredient-item">
                        <span className="ingredient-name">{ingredient.item.name}</span>
                        <span className="ingredient-percentage">{ingredient.percentage}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Total Quantity to Produce *</label>
                  <div className="input-with-unit">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      required
                      placeholder="0.00"
                    />
                    <div className="unit-toggle">
                      <button
                        type="button"
                        className={`toggle-btn ${quantityUnit === 'lbs' ? 'active' : ''}`}
                        onClick={() => setQuantityUnit('lbs')}
                      >
                        lbs
                      </button>
                      <button
                        type="button"
                        className={`toggle-btn ${quantityUnit === 'kg' ? 'active' : ''}`}
                        onClick={() => setQuantityUnit('kg')}
                      >
                        kg
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="lots-section">
                <label className="section-label">Select Lots (Available from Inventory) *</label>
                <p className="section-hint">Select specific lots and enter quantities to use for each ingredient</p>
                
                {selectedFormula.ingredients.map((ingredient) => {
                  // Match by SKU to allow vendor interchangeability
                  const ingredientLots = availableLots.filter(lot => lot.item.sku === ingredient.item.sku)
                  const totalSelected = Object.keys(selectedLots)
                    .filter(lotId => {
                      const lot = availableLots.find(l => l.id === parseInt(lotId))
                      return lot?.item.sku === ingredient.item.sku
                    })
                    .reduce((sum, lotId) => sum + (selectedLots[parseInt(lotId)] || 0), 0)
                  
                  const requiredQty = quantity ? (parseFloat(quantity) * (ingredient.percentage / 100)) : 0
                  const requiredQtyDisplay = quantityUnit === 'kg' 
                    ? convertWeight(requiredQty, 'lbs', 'kg').toFixed(2)
                    : requiredQty.toFixed(2)

                  return (
                    <div key={ingredient.id} className="ingredient-group">
                      <div className="ingredient-header">
                        <div className="ingredient-title">
                          <span className="ingredient-name">{ingredient.item.name}</span>
                          <span className="ingredient-percentage">{ingredient.percentage}% of batch</span>
                        </div>
                        <div className="ingredient-summary">
                          <span className="required-qty">
                            Required: {requiredQtyDisplay} {quantityUnit === 'kg' ? 'kg' : 'lbs'}
                          </span>
                          <span className={`selected-qty ${totalSelected > 0 ? 'has-selection' : ''}`}>
                            Selected: {totalSelected.toLocaleString()} {ingredientLots[0]?.unit_of_measure || 'lbs'}
                          </span>
                        </div>
                      </div>
                      
                      {ingredientLots.length === 0 ? (
                        <div className="no-lots-available">
                          ⚠️ No available lots for {ingredient.item.name}
                        </div>
                      ) : (
                        <div className="lots-grid">
                          {ingredientLots.map((lot) => (
                            <div key={lot.id} className={`lot-card ${selectedLots[lot.id] ? 'selected' : ''}`}>
                              <div className="lot-card-header">
                                <span className="lot-number-badge">{lot.lot_number}</span>
                                <span className="lot-available-badge">
                                  {lot.quantity_remaining.toLocaleString()} {lot.unit_of_measure} available
                                </span>
                              </div>
                              <div className="lot-quantity-section">
                                <label>Quantity to Use</label>
                                <div className="quantity-input-group">
                                  <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    max={lot.quantity_remaining}
                                    value={selectedLots[lot.id] || ''}
                                    onChange={(e) => handleLotQuantityChange(lot.id, e.target.value)}
                                    placeholder="0.00"
                                    className="quantity-input"
                                  />
                                  <span className="unit-label">{lot.unit_of_measure}</span>
                                </div>
                                {selectedLots[lot.id] && (
                                  <button
                                    type="button"
                                    onClick={() => handleLotQuantityChange(lot.id, '')}
                                    className="btn-clear-lot"
                                  >
                                    Clear
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !selectedFormula}>
              {submitting ? 'Creating...' : 'Create Batch Ticket'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateBatchTicket

