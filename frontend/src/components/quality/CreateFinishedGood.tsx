import { useState, useEffect } from 'react'
import { getItems, createItem, createFormula, getCriticalControlPoints } from '../../api/inventory'
import { getRDFormulas, getRDFormula } from '../../api/rdFormulas'
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
  const [ccps, setCcps] = useState<{ id: number; name: string }[]>([])
  const [approvedVendors, setApprovedVendors] = useState<any[]>([])
  const [rdFormulas, setRdFormulas] = useState<{ id: number; name: string; status: string }[]>([])
  const [selectedRdFormulaId, setSelectedRdFormulaId] = useState<number | ''>('')
  const [formData, setFormData] = useState({
    sku: '',
    name: '',
    description: '',
    pack_size: '',
    pack_size_unit: 'lbs' as 'lbs' | 'kg' | 'ea',
    formula_version: '1.0',
    shelf_life_months: '',
    critical_control_point_id: '' as string | number,
    qc_parameter_name: '',
    qc_spec_min: '',
    qc_spec_max: '',
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
      const [ccpsData, vendorsData, rdList] = await Promise.all([
        getCriticalControlPoints(),
        getVendors(),
        getRDFormulas().catch(() => []),
      ])
      setCcps(Array.isArray(ccpsData) ? ccpsData : [])
      setRdFormulas(Array.isArray(rdList) ? rdList.map((r: any) => ({ id: r.id, name: r.name, status: r.status || 'draft' })) : [])

      // Load vendors first to get approved vendor names
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

  const loadRDFormulaForPreFill = async (id: number) => {
    try {
      const rd = await getRDFormula(id) as { name: string; lines?: { line_type: string; item_id?: number; item?: { id: number }; composition_pct?: number; notes?: string }[] }
      setFormData((prev) => ({ ...prev, name: rd.name || prev.name }))
      const ingredientLines = (rd.lines || []).filter((l: any) => l.line_type === 'ingredient' && (l.item_id ?? l.item?.id))
      const preFillIngredients: FormulaIngredient[] = ingredientLines.length > 0
        ? ingredientLines.map((l: any) => ({
            item_id: String(l.item_id ?? l.item?.id ?? ''),
            percentage: l.composition_pct != null ? String(l.composition_pct) : '',
            notes: l.notes || '',
          }))
        : [{ item_id: '', percentage: '', notes: '' }]
      setIngredients(preFillIngredients)
    } catch (e) {
      console.error(e)
      alert('Could not load R&D formula')
    }
  }

  useEffect(() => {
    if (selectedRdFormulaId !== '' && typeof selectedRdFormulaId === 'number') {
      loadRDFormulaForPreFill(selectedRdFormulaId)
    }
  }, [selectedRdFormulaId])

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

    let shelfLifeMonths: number | null = null
    if (formData.shelf_life_months.trim()) {
      const n = parseInt(formData.shelf_life_months, 10)
      if (Number.isNaN(n) || n < 1) {
        alert('Shelf life (months) must be a positive whole number, or leave blank.')
        return
      }
      shelfLifeMonths = n
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
        shelf_life_months: shelfLifeMonths,
        critical_control_point_id: formData.critical_control_point_id ? Number(formData.critical_control_point_id) : null,
        qc_parameter_name: formData.qc_parameter_name?.trim() || null,
        qc_spec_min: formData.qc_spec_min?.trim() ? parseFloat(formData.qc_spec_min) : null,
        qc_spec_max: formData.qc_spec_max?.trim() ? parseFloat(formData.qc_spec_max) : null,
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
        <div className="form-section rd-formula-prefill-section">
          <h3>Start from R&D formula (optional)</h3>
          <p className="form-hint">Select an approved R&D formula to pre-fill product name and ingredient list.</p>
          <div className="form-group">
            <label>R&D Formula</label>
            <select
              value={selectedRdFormulaId === '' ? '' : String(selectedRdFormulaId)}
              onChange={(e) => setSelectedRdFormulaId(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
              className="rd-formula-select"
            >
              <option value="">— None —</option>
              {rdFormulas.map((r) => (
                <option key={r.id} value={r.id}>{r.name} ({r.status})</option>
              ))}
            </select>
          </div>
        </div>

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
            <div className="form-group">
              <label>Shelf life (months)</label>
              <input
                type="number"
                min={1}
                max={120}
                step={1}
                value={formData.shelf_life_months}
                onChange={(e) => setFormData({ ...formData, shelf_life_months: e.target.value })}
                placeholder="e.g. 24"
              />
              <small className="form-hint">Default expiration for new FG lots = batch close date + this many months. Optional.</small>
            </div>
            <div className="form-group">
              <label>Critical Control Point (CCP)</label>
              <select
                value={formData.critical_control_point_id === '' ? '' : String(formData.critical_control_point_id)}
                onChange={(e) => setFormData({ ...formData, critical_control_point_id: e.target.value === '' ? '' : Number(e.target.value) })}
              >
                <option value="">None</option>
                {ccps.map((ccp) => (
                  <option key={ccp.id} value={ccp.id}>{ccp.name}</option>
                ))}
              </select>
              <small className="form-hint">Shown on batch ticket: &quot;Has [CCP] been inspected and installed properly?&quot;</small>
            </div>
          </div>

          <div className="form-section qc-section">
            <h3>Quality Control Parameters</h3>
            <div className="form-grid">
              <div className="form-group full-width">
                <label>QC Parameter Name</label>
                <input
                  type="text"
                  value={formData.qc_parameter_name}
                  onChange={(e) => setFormData({ ...formData, qc_parameter_name: e.target.value })}
                  placeholder="e.g., norbixin, betanin, absorbance"
                />
                <small className="form-hint">This parameter will be required when closing batches for this finished good.</small>
              </div>
              <div className="form-group">
                <label>Spec Minimum</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.qc_spec_min}
                  onChange={(e) => setFormData({ ...formData, qc_spec_min: e.target.value })}
                  placeholder="Min value"
                />
              </div>
              <div className="form-group">
                <label>Spec Maximum</label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.qc_spec_max}
                  onChange={(e) => setFormData({ ...formData, qc_spec_max: e.target.value })}
                  placeholder="Max value"
                />
              </div>
            </div>
            <p className="qc-note">If both min and max are set, batch closure will validate that QC results fall within this range. Leave blank if no QC validation is required.</p>
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

