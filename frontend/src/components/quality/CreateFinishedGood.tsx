import { useState, useEffect } from 'react'
import { getItems, createItem, createFormula } from '../../api/inventory'
import { getVendors } from '../../api/quality'
import './CreateFinishedGood.css'

interface FormulaIngredient {
  item_id: string
  percentage: string
  notes: string
}

interface CreateFinishedGoodProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateFinishedGood({ onClose = () => {}, onSuccess = () => {} }: CreateFinishedGoodProps) {
  const [items, setItems] = useState<any[]>([])
  const [approvedVendors, setApprovedVendors] = useState<any[]>([])
  const [formData, setFormData] = useState({
    sku: '',
    name: '',
    description: '',
    pack_size: '',
    pack_size_unit: 'lbs' as 'lbs' | 'kg' | 'ea',
    formula_version: '1.0',
    mixing_instructions: '',
    order_of_addition: '',
    equipment: '',
    formula_notes: '',
  })
  const [ingredients, setIngredients] = useState<FormulaIngredient[]>([
    { item_id: '', percentage: '', notes: '' }
  ])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      // Load vendors first to get approved vendor names
      const vendorsData = await getVendors()
      console.log('All vendors:', vendorsData)
      const approved = vendorsData.filter((v: any) => v.approval_status === 'approved')
      console.log('Approved vendors:', approved)
      setApprovedVendors(approved)
      
      // Load items and filter by approved vendors
      const itemsData = await getItems()
      console.log('All items:', itemsData)
      const approvedVendorNames = approved.map((v: any) => v.name)
      console.log('Approved vendor names:', approvedVendorNames)
      
      // Only show raw materials and distributed items from approved vendors
      const filteredItems = itemsData.filter((item: any) => {
        const isCorrectType = item.item_type === 'raw_material' || item.item_type === 'distributed_item'
        const hasVendor = item.vendor && item.vendor.trim() !== ''
        const vendorIsApproved = hasVendor && approvedVendorNames.includes(item.vendor)
        
        console.log(`Item ${item.sku}: type=${isCorrectType}, vendor=${item.vendor}, vendorApproved=${vendorIsApproved}`)
        
        return isCorrectType && hasVendor && vendorIsApproved
      })
      
      // Group items by SKU - keep only one item per SKU (prefer the first one found)
      // This allows interchangeability of materials from different vendors
      const itemsBySku = new Map<string, any>()
      filteredItems.forEach((item: any) => {
        if (!itemsBySku.has(item.sku)) {
          itemsBySku.set(item.sku, item)
        }
      })
      
      // Convert map to array - items are now unique by SKU
      const uniqueItems = Array.from(itemsBySku.values())
      
      console.log('Unique items by SKU (for formula ingredients):', uniqueItems.length, uniqueItems)
      setItems(uniqueItems)
      
      if (uniqueItems.length === 0) {
        console.warn('No items found. Check: 1) Items have vendors assigned, 2) Vendors are approved, 3) Items are approved for formulas')
      }
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load items. Make sure vendors are approved in the Quality tab.')
    }
  }

  const addIngredient = () => {
    setIngredients([...ingredients, { item_id: '', percentage: '', notes: '' }])
  }

  const removeIngredient = (index: number) => {
    if (ingredients.length > 1) {
      setIngredients(ingredients.filter((_, i) => i !== index))
    }
  }

  const updateIngredient = (index: number, field: keyof FormulaIngredient, value: string) => {
    const newIngredients = [...ingredients]
    newIngredients[index] = { ...newIngredients[index], [field]: value }
    setIngredients(newIngredients)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.sku || !formData.name) {
      alert('Please fill in SKU and name')
      return
    }

    // Validate ingredients
    const validIngredients = ingredients.filter(ing => ing.item_id && ing.percentage)
    if (validIngredients.length === 0) {
      alert('Please add at least one formula ingredient')
      return
    }

    const totalPercentage = validIngredients.reduce((sum, ing) => sum + parseFloat(ing.percentage || '0'), 0)
    if (Math.abs(totalPercentage - 100) > 0.01) {
      alert(`Total percentage must equal 100%. Current total: ${totalPercentage.toFixed(2)}%`)
      return
    }

    try {
      setSubmitting(true)
      
      // Create the finished good item
      const itemResponse = await createItem({
        sku: formData.sku,
        name: formData.name,
        description: formData.description,
        item_type: 'finished_good',
        unit_of_measure: formData.pack_size_unit,
        pack_size: parseFloat(formData.pack_size || '1'),
      })
      
      // Create the formula
      await createFormula({
        finished_good_id: itemResponse.id,
        version: formData.formula_version,
        mixing_instructions: formData.mixing_instructions || null,
        order_of_addition: formData.order_of_addition || null,
        equipment: formData.equipment || null,
        notes: formData.formula_notes || null,
        ingredients: validIngredients.map(ing => ({
          item_id: parseInt(ing.item_id),
          percentage: parseFloat(ing.percentage),
          notes: ing.notes || null,
        }))
      })
      
      alert('Finished good and formula created successfully!')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create finished good:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create finished good')
    } finally {
      setSubmitting(false)
    }
  }

  const totalPercentage = ingredients
    .filter(ing => ing.percentage)
    .reduce((sum, ing) => sum + parseFloat(ing.percentage || '0'), 0)

  return (
    <div className="create-finished-good">
      <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2>Create Finished Good</h2>
          <p style={{ margin: '5px 0 0 0', color: '#666' }}>Create a new finished good item with its formula, mixing instructions, and equipment requirements</p>
        </div>
        <button onClick={onClose} className="close-btn" style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', padding: '0 10px' }}>×</button>
      </div>

      <form onSubmit={handleSubmit} className="finished-good-form">
        <div className="form-section">
          <h3>Item Information</h3>
          <div className="form-grid">
            <div className="form-group">
              <label>WWI Item Number (SKU) *</label>
              <input
                type="text"
                value={formData.sku}
                onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Item Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group full-width">
              <label>Description</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>

            <div className="form-group">
              <label>Pack Size</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.pack_size}
                  onChange={(e) => setFormData({ ...formData, pack_size: e.target.value })}
                  placeholder="1.0"
                />
                <select
                  value={formData.pack_size_unit}
                  onChange={(e) => setFormData({ ...formData, pack_size_unit: e.target.value as 'lbs' | 'kg' | 'ea' })}
                >
                  <option value="lbs">lbs</option>
                  <option value="kg">kg</option>
                  <option value="ea">ea</option>
                </select>
              </div>
            </div>

          </div>
        </div>

        <div className="form-section">
          <h3>Formula</h3>
          <div className="form-grid">
            <div className="form-group">
              <label>Formula Version *</label>
              <input
                type="text"
                value={formData.formula_version}
                onChange={(e) => setFormData({ ...formData, formula_version: e.target.value })}
                required
                placeholder="1.0"
              />
            </div>
          </div>

          <div className="ingredients-section">
            <div className="ingredients-header">
              <h4>Formula Ingredients (Total must equal 100%)</h4>
              <div className="percentage-total">
                Total: <span className={Math.abs(totalPercentage - 100) < 0.01 ? 'balanced' : 'unbalanced'}>
                  {totalPercentage.toFixed(2)}%
                </span>
              </div>
              <button type="button" onClick={addIngredient} className="btn btn-secondary btn-sm">
                + Add Ingredient
              </button>
            </div>

            <div className="ingredients-list">
              {ingredients.map((ingredient, index) => (
                <div key={index} className="ingredient-row">
                  <select
                    value={ingredient.item_id}
                    onChange={(e) => updateIngredient(index, 'item_id', e.target.value)}
                    required
                    className="ingredient-select"
                  >
                    <option value="">Select Ingredient</option>
                    {items.length === 0 ? (
                      <option value="" disabled>No items from approved vendors available</option>
                    ) : (
                      items.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.sku} - {item.name}
                        </option>
                      ))
                    )}
                  </select>
                  {items.length === 0 && (
                    <div style={{ color: '#e74c3c', fontSize: '0.85rem', marginTop: '0.25rem', marginBottom: '0.5rem' }}>
                      No items available. Please ensure:
                      <ul style={{ margin: '0.25rem 0', paddingLeft: '1.5rem' }}>
                        <li>Items have vendors assigned</li>
                        <li>Vendors are approved in the Quality tab</li>
                        <li>Items are raw materials or distributed items</li>
                      </ul>
                    </div>
                  )}
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    value={ingredient.percentage}
                    onChange={(e) => updateIngredient(index, 'percentage', e.target.value)}
                    placeholder="%"
                    required
                    className="percentage-input"
                  />
                  <input
                    type="text"
                    value={ingredient.notes}
                    onChange={(e) => updateIngredient(index, 'notes', e.target.value)}
                    placeholder="Notes (optional)"
                    className="notes-input"
                  />
                  {ingredients.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeIngredient(index)}
                      className="btn-remove"
                    >
                      Remove
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="form-section">
          <h3>Production Instructions</h3>
          <div className="form-grid">
            <div className="form-group full-width">
              <label>Mixing Instructions</label>
              <textarea
                value={formData.mixing_instructions}
                onChange={(e) => setFormData({ ...formData, mixing_instructions: e.target.value })}
                rows={4}
                placeholder="Enter detailed mixing instructions..."
              />
            </div>

            <div className="form-group full-width">
              <label>Order of Addition</label>
              <textarea
                value={formData.order_of_addition}
                onChange={(e) => setFormData({ ...formData, order_of_addition: e.target.value })}
                rows={4}
                placeholder="Enter the order in which ingredients should be added..."
              />
            </div>

            <div className="form-group">
              <label>Equipment</label>
              <input
                type="text"
                value={formData.equipment}
                onChange={(e) => setFormData({ ...formData, equipment: e.target.value })}
                placeholder="e.g., Mixer Model XYZ, Temperature: 150°F"
              />
            </div>

            <div className="form-group full-width">
              <label>Formula Notes</label>
              <textarea
                value={formData.formula_notes}
                onChange={(e) => setFormData({ ...formData, formula_notes: e.target.value })}
                rows={3}
                placeholder="Additional notes about the formula..."
              />
            </div>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" onClick={onClose} className="btn btn-secondary">
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting || Math.abs(totalPercentage - 100) > 0.01}>
            {submitting ? 'Creating...' : 'Create Finished Good'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default CreateFinishedGood

