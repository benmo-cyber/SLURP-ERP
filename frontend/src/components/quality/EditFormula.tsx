import { useState, useEffect } from 'react'
import { getItems, getFormulas, getCriticalControlPoints, updateFormula } from '../../api/inventory'
import { getVendors } from '../../api/quality'
import './CreateFinishedGood.css'

interface FormulaIngredient {
  id?: number
  item_id: string
  percentage: string
  notes: string
}

interface EditFormulaProps {
  finishedGoodId: number
  finishedGoodSku: string
  finishedGoodName: string
  onClose: () => void
  onSuccess: () => void
}

function EditFormula({ finishedGoodId, finishedGoodSku, finishedGoodName, onClose, onSuccess }: EditFormulaProps) {
  const [items, setItems] = useState<any[]>([])
  const [ccps, setCcps] = useState<{ id: number; name: string; display_order: number }[]>([])
  const [formula, setFormula] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [formData, setFormData] = useState({
    formula_version: '1.0',
    formula_notes: '',
    critical_control_point_id: '' as string | number,
    qc_parameter_name: '',
    qc_spec_min: '',
    qc_spec_max: '',
    mixing_step_1: '',
    mixing_step_2: '',
    mixing_step_3: '',
    mixing_step_4: '',
    mixing_step_5: '',
    mixing_step_6: '',
  })
  const [ingredients, setIngredients] = useState<FormulaIngredient[]>([
    { item_id: '', percentage: '', notes: '' }
  ])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadData()
  }, [finishedGoodId])

  const loadData = async () => {
    try {
      setLoading(true)
      // Load vendors first to get approved vendor names
      const vendorsData = await getVendors()
      const approved = vendorsData.filter((v: any) => v.approval_status === 'approved')
      
      // Load items and filter by approved vendors
      const itemsData = await getItems()
      const approvedVendorNames = approved.map((v: any) => v.name)
      
      const filteredItems = itemsData.filter((item: any) => {
        const isCorrectType = item.item_type === 'raw_material' || item.item_type === 'distributed_item'
        const hasVendor = item.vendor && item.vendor.trim() !== ''
        const vendorIsApproved = hasVendor && approvedVendorNames.includes(item.vendor)
        return isCorrectType && hasVendor && vendorIsApproved
      })
      
      // Group items by SKU
      const itemsBySku = new Map<string, any>()
      filteredItems.forEach((item: any) => {
        if (!itemsBySku.has(item.sku)) {
          itemsBySku.set(item.sku, item)
        }
      })
      const uniqueItems = Array.from(itemsBySku.values())
      setItems(uniqueItems)

      const ccpsData = await getCriticalControlPoints()
      setCcps(ccpsData)
      
      // Load the formula
      const formulas = await getFormulas()
      const foundFormula = formulas.find((f: any) => f.finished_good?.id === finishedGoodId)
      
      if (foundFormula) {
        setFormula(foundFormula)
        setFormData({
          formula_version: foundFormula.version || '1.0',
          formula_notes: foundFormula.notes || '',
          qc_parameter_name: foundFormula.qc_parameter_name || '',
          qc_spec_min: foundFormula.qc_spec_min !== null && foundFormula.qc_spec_min !== undefined ? String(foundFormula.qc_spec_min) : '',
          qc_spec_max: foundFormula.qc_spec_max !== null && foundFormula.qc_spec_max !== undefined ? String(foundFormula.qc_spec_max) : '',
          mixing_step_1: foundFormula.mixing_step_1 || '',
          mixing_step_2: foundFormula.mixing_step_2 || '',
          mixing_step_3: foundFormula.mixing_step_3 || '',
          mixing_step_4: foundFormula.mixing_step_4 || '',
          mixing_step_5: foundFormula.mixing_step_5 || '',
          mixing_step_6: foundFormula.mixing_step_6 || '',
        })
        
        // Load ingredients
        if (foundFormula.ingredients && foundFormula.ingredients.length > 0) {
          setIngredients(foundFormula.ingredients.map((ing: any) => ({
            id: ing.id,
            item_id: String(ing.item?.id || ''),
            percentage: String(ing.percentage || ''),
            notes: ing.notes || '',
          })))
        }
      }
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load formula data')
    } finally {
      setLoading(false)
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

    if (!formula) {
      alert('Formula not found')
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
      
      // Update the formula
      await updateFormula(formula.id, {
        finished_good_id: finishedGoodId,
        version: formData.formula_version,
        notes: formData.formula_notes || null,
        critical_control_point_id: formData.critical_control_point_id ? Number(formData.critical_control_point_id) : null,
        qc_parameter_name: formData.qc_parameter_name.trim() || null,
        qc_spec_min: formData.qc_spec_min.trim() ? parseFloat(formData.qc_spec_min) : null,
        qc_spec_max: formData.qc_spec_max.trim() ? parseFloat(formData.qc_spec_max) : null,
        mixing_step_1: formData.mixing_step_1.trim() || null,
        mixing_step_2: formData.mixing_step_2.trim() || null,
        mixing_step_3: formData.mixing_step_3.trim() || null,
        mixing_step_4: formData.mixing_step_4.trim() || null,
        mixing_step_5: formData.mixing_step_5.trim() || null,
        mixing_step_6: formData.mixing_step_6.trim() || null,
        ingredients: validIngredients.map(ing => ({
          item_id: parseInt(ing.item_id),
          percentage: parseFloat(ing.percentage),
          notes: ing.notes || null,
        }))
      })
      
      alert('Formula updated successfully!')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to update formula:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to update formula')
    } finally {
      setSubmitting(false)
    }
  }

  const totalPercentage = ingredients
    .filter(ing => ing.percentage)
    .reduce((sum, ing) => sum + parseFloat(ing.percentage || '0'), 0)

  if (loading) {
    return (
      <div className="create-finished-good">
        <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h2>Edit Formula</h2>
            <p style={{ margin: '5px 0 0 0', color: '#666' }}>Loading formula data...</p>
          </div>
          <button onClick={onClose} className="close-btn" style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', padding: '0 10px' }}>×</button>
        </div>
      </div>
    )
  }

  if (!formula) {
    return (
      <div className="create-finished-good">
        <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h2>Edit Formula</h2>
            <p style={{ margin: '5px 0 0 0', color: '#666' }}>No formula found for this finished good.</p>
          </div>
          <button onClick={onClose} className="close-btn" style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', padding: '0 10px' }}>×</button>
        </div>
        <div className="form-actions">
          <button onClick={onClose} className="btn btn-secondary">Close</button>
        </div>
      </div>
    )
  }

  return (
    <div className="create-finished-good">
      <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2>Edit Formula</h2>
          <p style={{ margin: '5px 0 0 0', color: '#666' }}>{finishedGoodSku} - {finishedGoodName}</p>
        </div>
        <button onClick={onClose} className="close-btn" style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', padding: '0 10px' }}>×</button>
      </div>

      <form onSubmit={handleSubmit} className="finished-good-form">
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
              <label>Critical Control Point (CCP)</label>
              <select
                value={formData.critical_control_point_id === '' ? '' : String(formData.critical_control_point_id)}
                onChange={(e) => setFormData({ ...formData, critical_control_point_id: e.target.value === '' ? '' : Number(e.target.value) })}
              >
                <option value="">None (use default on batch ticket)</option>
                {ccps.map((ccp) => (
                  <option key={ccp.id} value={ccp.id}>{ccp.name}</option>
                ))}
              </select>
              <small style={{ color: '#666', display: 'block', marginTop: '0.25rem' }}>
                Shown on batch ticket pre-production: &quot;Has [CCP] been inspected and installed properly?&quot;
              </small>
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
                    {items.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.sku} - {item.name}
                      </option>
                    ))}
                  </select>
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
          <h3>Mixing Steps</h3>
          <p style={{ margin: '0 0 0.75rem 0', color: '#666', fontSize: '0.875rem' }}>
            Enter mixing instructions for batch production (Steps 1–6). Optional.
          </p>
          <div className="form-grid" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {[1, 2, 3, 4, 5, 6].map((step) => (
              <div key={step} className="form-group" style={{ width: '100%' }}>
                <label>Step {step}</label>
                <textarea
                  value={formData[`mixing_step_${step}` as keyof typeof formData] as string}
                  onChange={(e) => setFormData({ ...formData, [`mixing_step_${step}`]: e.target.value })}
                  rows={2}
                  placeholder={`Mixing step ${step}...`}
                  style={{ width: '100%', resize: 'vertical' }}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="form-section">
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
              <small style={{ color: '#666', display: 'block', marginTop: '0.25rem' }}>
                This parameter will be required when closing batches for this finished good
              </small>
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
          <div style={{ 
            padding: '0.75rem', 
            marginTop: '1rem', 
            backgroundColor: '#f0f9ff', 
            borderRadius: '6px',
            border: '1px solid #0284c7',
            fontSize: '0.875rem',
            color: '#0369a1'
          }}>
            <strong>Note:</strong> If both min and max are specified, batch closure will validate that QC results fall within this range. 
            Leave blank if no QC validation is required.
          </div>
        </div>

        <div className="form-section">
          <h3>Formula Notes</h3>
          <div className="form-grid">
            <div className="form-group full-width">
              <label>Notes</label>
              <textarea
                value={formData.formula_notes}
                onChange={(e) => setFormData({ ...formData, formula_notes: e.target.value })}
                rows={4}
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
            {submitting ? 'Updating...' : 'Update Formula'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default EditFormula
