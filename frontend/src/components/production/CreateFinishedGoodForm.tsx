import { useState, useEffect } from 'react'
import { getItems, createItem } from '../../api/inventory'
import { createFinishedProductSpecification } from '../../api/production'
import './CreateFinishedGoodForm.css'

interface CreateFinishedGoodFormProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateFinishedGoodForm({ onClose, onSuccess }: CreateFinishedGoodFormProps) {
  const [submitting, setSubmitting] = useState(false)
  const [step, setStep] = useState<'item' | 'fps'>('item')
  
  // Item form data
  const [itemData, setItemData] = useState({
    sku: '',
    name: '',
    description: '',
    unit_of_measure: 'lbs' as 'lbs' | 'kg' | 'ea',
    pack_size: '',
    price: '',
  })
  
  // FPS form data
  const [fpsData, setFpsData] = useState({
    test_frequency: '',
    product_description: '',
    color_specification: '',
    ph: '',
    water_activity: '',
    microbiological_requirements: '',
    shelf_life_storage: '',
    packaging_type: '',
    additional_criteria: '',
    msds_created: false,
    commercial_spec_created: false,
    label_template_created: false,
    micro_growth_evaluated: false,
    kosher_letter_added: false,
    haccp_plan_created: false,
    processing_requirements: '',
    completed_by_name: '',
    completed_by_signature: '',
    completed_date: '',
  })
  
  const [createdItemId, setCreatedItemId] = useState<number | null>(null)

  const handleItemSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!itemData.sku || !itemData.name) {
      alert('Please fill in SKU and Name')
      return
    }

    try {
      setSubmitting(true)
      const payload: any = {
        sku: itemData.sku,
        name: itemData.name,
        description: itemData.description || null,
        item_type: 'finished_good',
        unit_of_measure: itemData.unit_of_measure,
      }
      
      if (itemData.pack_size) {
        payload.pack_size = parseFloat(itemData.pack_size)
      }
      if (itemData.price) {
        payload.price = parseFloat(itemData.price)
      }
      
      const item = await createItem(payload)
      setCreatedItemId(item.id)
      setStep('fps')
    } catch (error: any) {
      console.error('Failed to create item:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to create finished good')
    } finally {
      setSubmitting(false)
    }
  }

  const handleFpsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!createdItemId) {
      alert('Item must be created first')
      return
    }

    try {
      setSubmitting(true)
      const payload: any = {
        item_id: createdItemId,
        ...fpsData,
      }
      
      // Convert empty strings to null
      Object.keys(payload).forEach(key => {
        if (payload[key] === '') {
          payload[key] = null
        }
      })
      
      await createFinishedProductSpecification(payload)
      alert('Finished Good and FPS created successfully! PDF has been generated.')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create FPS:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to create FPS')
    } finally {
      setSubmitting(false)
    }
  }

  const handleChange = (field: string, value: any) => {
    if (step === 'item') {
      setItemData({ ...itemData, [field]: value })
    } else {
      setFpsData({ ...fpsData, [field]: value })
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-finished-good-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Finished Good {step === 'fps' ? '- FPS Information' : ''}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        {step === 'item' ? (
          <form onSubmit={handleItemSubmit} className="fps-form">
            <div className="form-section">
              <h3>Item Information</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label htmlFor="sku">WWI Item Number (SKU) *</label>
                  <input
                    type="text"
                    id="sku"
                    value={itemData.sku}
                    onChange={(e) => handleChange('sku', e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="name">Product Name *</label>
                  <input
                    type="text"
                    id="name"
                    value={itemData.name}
                    onChange={(e) => handleChange('name', e.target.value)}
                    required
                  />
                </div>

                <div className="form-group full-width">
                  <label htmlFor="description">Description</label>
                  <textarea
                    id="description"
                    rows={3}
                    value={itemData.description}
                    onChange={(e) => handleChange('description', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="unit_of_measure">Unit of Measure *</label>
                  <select
                    id="unit_of_measure"
                    value={itemData.unit_of_measure}
                    onChange={(e) => handleChange('unit_of_measure', e.target.value)}
                    required
                  >
                    <option value="lbs">lbs</option>
                    <option value="kg">kg</option>
                    <option value="ea">ea</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="pack_size">Pack Size</label>
                  <input
                    type="number"
                    step="0.01"
                    id="pack_size"
                    value={itemData.pack_size}
                    onChange={(e) => handleChange('pack_size', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="price">Price</label>
                  <input
                    type="number"
                    step="0.01"
                    id="price"
                    value={itemData.price}
                    onChange={(e) => handleChange('price', e.target.value)}
                  />
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? 'Creating...' : 'Next: FPS Information'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleFpsSubmit} className="fps-form">
            <div className="form-section">
              <h3>Finished Product Specification</h3>
              
              <div className="form-group">
                <label htmlFor="test_frequency">Test frequency</label>
                <input
                  type="text"
                  id="test_frequency"
                  value={fpsData.test_frequency}
                  onChange={(e) => handleChange('test_frequency', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="product_description">Product Description<br/>(physical state, color, odor, etc.)</label>
                <textarea
                  id="product_description"
                  rows={3}
                  value={fpsData.product_description}
                  onChange={(e) => handleChange('product_description', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="color_specification">Color Specification<br/>(CV, dye %, color strength, etc.)</label>
                <textarea
                  id="color_specification"
                  rows={2}
                  value={fpsData.color_specification}
                  onChange={(e) => handleChange('color_specification', e.target.value)}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="ph">pH</label>
                  <input
                    type="text"
                    id="ph"
                    value={fpsData.ph}
                    onChange={(e) => handleChange('ph', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="water_activity">Water Activity (aW)</label>
                  <input
                    type="text"
                    id="water_activity"
                    value={fpsData.water_activity}
                    onChange={(e) => handleChange('water_activity', e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="microbiological_requirements">Microbiological Requirements<br/>(if micro testing not required, rationale must be provided)</label>
                <textarea
                  id="microbiological_requirements"
                  rows={3}
                  value={fpsData.microbiological_requirements}
                  onChange={(e) => handleChange('microbiological_requirements', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="shelf_life_storage">Shelf life / Storage Requirements<br/>(temperature data)<br/>Include Basis for decision and record Shelf-Life Assignment Form (Document No. 5.1.4–03)<br/>Shelf-Life Study Log (Document No. 5.1.4–02)</label>
                <textarea
                  id="shelf_life_storage"
                  rows={4}
                  value={fpsData.shelf_life_storage}
                  onChange={(e) => handleChange('shelf_life_storage', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="packaging_type">Type of Packaging</label>
                <input
                  type="text"
                  id="packaging_type"
                  value={fpsData.packaging_type}
                  onChange={(e) => handleChange('packaging_type', e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="additional_criteria">Additional Criteria<br/>(physical parameter testing, flavor profile, customer considerations, etc.)</label>
                <textarea
                  id="additional_criteria"
                  rows={3}
                  value={fpsData.additional_criteria}
                  onChange={(e) => handleChange('additional_criteria', e.target.value)}
                />
              </div>
            </div>

            <div className="form-section">
              <h3>FPS Checklist</h3>
              
              <div className="checklist-grid">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.msds_created}
                    onChange={(e) => handleChange('msds_created', e.target.checked)}
                  />
                  <span>MSDS Created</span>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.commercial_spec_created}
                    onChange={(e) => handleChange('commercial_spec_created', e.target.checked)}
                  />
                  <span>Commercial Spec Created / COA</span>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.label_template_created}
                    onChange={(e) => handleChange('label_template_created', e.target.checked)}
                  />
                  <span>Label Template Created</span>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.micro_growth_evaluated}
                    onChange={(e) => handleChange('micro_growth_evaluated', e.target.checked)}
                  />
                  <span>Product evaluated for micro growth</span>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.kosher_letter_added}
                    onChange={(e) => handleChange('kosher_letter_added', e.target.checked)}
                  />
                  <span>Product Added to Kosher Letter</span>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={fpsData.haccp_plan_created}
                    onChange={(e) => handleChange('haccp_plan_created', e.target.checked)}
                  />
                  <span>Initial HACCP Plan Created</span>
                </label>
              </div>

              <div className="form-group">
                <label htmlFor="processing_requirements">Processing Requirements<br/>(i.e. specific tank or mixer, how long should product be mixed, allergen considerations, temperature requirements)</label>
                <textarea
                  id="processing_requirements"
                  rows={4}
                  value={fpsData.processing_requirements}
                  onChange={(e) => handleChange('processing_requirements', e.target.value)}
                />
              </div>
            </div>

            <div className="form-section">
              <h3>Completion Information</h3>
              
              <div className="form-group">
                <label htmlFor="completed_by_name">Name and Title of Person Completing Form</label>
                <input
                  type="text"
                  id="completed_by_name"
                  value={fpsData.completed_by_name}
                  onChange={(e) => handleChange('completed_by_name', e.target.value)}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="completed_by_signature">Signature</label>
                  <input
                    type="text"
                    id="completed_by_signature"
                    value={fpsData.completed_by_signature}
                    onChange={(e) => handleChange('completed_by_signature', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="completed_date">Date</label>
                  <input
                    type="date"
                    id="completed_date"
                    value={fpsData.completed_date}
                    onChange={(e) => handleChange('completed_date', e.target.value)}
                  />
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button type="button" onClick={() => setStep('item')} className="btn btn-secondary">
                ← Back
              </button>
              <button type="button" onClick={onClose} className="btn btn-secondary">
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? 'Creating...' : 'Create Finished Good & Generate FPS'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

export default CreateFinishedGoodForm
