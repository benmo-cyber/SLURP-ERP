import { useState, useEffect } from 'react'
import { getItems, createItem } from '../../api/inventory'
import { getVendors } from '../../api/quality'
import './CreateItemForm.css'

interface Vendor {
  id: number
  name: string
  approval_status: string
}

interface CreateItemFormProps {
  onClose: () => void
  onSuccess: () => void
}

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  item_type: string
  unit_of_measure: string
  vendor?: string
}

function CreateItemForm({ onClose, onSuccess }: CreateItemFormProps) {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [existingItems, setExistingItems] = useState<Item[]>([])
  const [mode, setMode] = useState<'new' | 'add-vendor'>('new')
  const [selectedItem, setSelectedItem] = useState<Item | null>(null)
  const [formData, setFormData] = useState({
    vendor: '',
    vendor_item_number: '',
    wwi_item_number: '',
    name: '',
    description: '',
    pack_size: '',
    unit_of_measure: 'lbs' as 'lbs' | 'kg' | 'ea',
    price: '',
    item_type: 'raw_material' as 'raw_material' | 'distributed_item' | 'finished_good' | 'indirect_material',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadVendors()
    loadExistingItems()
  }, [])

  useEffect(() => {
    if (mode === 'add-vendor' && selectedItem) {
      // Pre-fill form with selected item data
      setFormData({
        ...formData,
        wwi_item_number: selectedItem.sku,
        name: selectedItem.name,
        description: selectedItem.description || '',
        item_type: selectedItem.item_type as any,
        unit_of_measure: selectedItem.unit_of_measure as 'lbs' | 'kg' | 'ea',
        // Clear vendor-specific fields
        vendor: '',
        pack_size: '',
        price: '',
      })
    } else if (mode === 'new') {
      // Reset form
      setFormData({
        vendor: '',
        vendor_item_number: '',
        wwi_item_number: '',
        name: '',
        description: '',
        pack_size: '',
        unit_of_measure: 'lbs',
        price: '',
        item_type: 'raw_material',
      })
      setSelectedItem(null)
    }
  }, [mode, selectedItem])

  const loadVendors = async () => {
    try {
      const data = await getVendors()
      // Only show approved vendors
      const approvedVendors = data.filter((vendor: Vendor) => vendor.approval_status === 'approved')
      setVendors(approvedVendors)
    } catch (error) {
      console.error('Failed to load vendors:', error)
      // If no approved vendors, show empty list
      setVendors([])
    }
  }

  const loadExistingItems = async () => {
    try {
      const data = await getItems()
      setExistingItems(data)
    } catch (error) {
      console.error('Failed to load existing items:', error)
    }
  }

  const handleItemSelect = (item: Item) => {
    setSelectedItem(item)
    // Filter out vendors that already have this item
    const existingVendors = existingItems
      .filter(i => i.sku === item.sku && i.vendor)
      .map(i => i.vendor)
    const availableVendors = vendors.filter(v => !existingVendors.includes(v.name))
    // If no available vendors, show message
    if (availableVendors.length === 0) {
      alert('All approved vendors already have this item. Please approve more vendors or select a different item.')
      return
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('Form submitted', formData)

    if (!formData.vendor || !formData.wwi_item_number || !formData.name) {
      alert('Please fill in all required fields (Vendor, WWI Item Number, and Name)')
      return
    }

    // Check if this SKU + vendor combination already exists
    if (mode === 'add-vendor') {
      const existing = existingItems.find(
        i => i.sku === formData.wwi_item_number && i.vendor === formData.vendor
      )
      if (existing) {
        alert(`This item (${formData.wwi_item_number}) already exists for vendor ${formData.vendor}. Please select a different vendor.`)
        return
      }
    }
    
    // Validate pack_size and price if provided
    if (formData.pack_size && typeof formData.pack_size === 'string' && formData.pack_size.trim() !== '') {
      const packSizeValue = parseFloat(formData.pack_size)
      if (isNaN(packSizeValue) || packSizeValue <= 0) {
        alert('Pack size must be a positive number')
        return
      }
    }
    
    if (formData.price && typeof formData.price === 'string' && formData.price.trim() !== '') {
      const priceValue = parseFloat(formData.price)
      if (isNaN(priceValue) || priceValue <= 0) {
        alert('Price must be a positive number')
        return
      }
    }

    let payload: any = {}
    
    try {
      setSubmitting(true)
      
      payload = {
        sku: formData.wwi_item_number,
        name: formData.name,
        description: formData.description || null,
        item_type: formData.item_type,
        unit_of_measure: formData.unit_of_measure,
        vendor: formData.vendor || null,
      }
      
      // Only include pack_size and price if they have values
      if (formData.pack_size && typeof formData.pack_size === 'string' && formData.pack_size.trim() !== '') {
        const packSizeValue = parseFloat(formData.pack_size)
        if (!isNaN(packSizeValue) && packSizeValue > 0) {
          payload.pack_size = packSizeValue
        }
      }
      
      if (formData.price && typeof formData.price === 'string' && formData.price.trim() !== '') {
        const priceValue = parseFloat(formData.price)
        if (!isNaN(priceValue) && priceValue > 0) {
          payload.price = priceValue
        }
      }
      
      await createItem(payload)
      
      alert('Item created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create item:', error)
      console.error('Error response:', error.response?.data)
      console.error('Payload sent:', payload)
      const errorMessage = error.response?.data?.detail || 
                          error.response?.data?.message || 
                          (typeof error.response?.data === 'object' ? JSON.stringify(error.response.data) : error.message) ||
                          'Failed to create item'
      alert(`Failed to create item: ${errorMessage}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-item-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{mode === 'add-vendor' ? 'Add Vendor Variant' : 'Create New Item'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="form-mode-selector">
          <button
            type="button"
            className={`mode-btn ${mode === 'new' ? 'active' : ''}`}
            onClick={() => setMode('new')}
          >
            New Item
          </button>
          <button
            type="button"
            className={`mode-btn ${mode === 'add-vendor' ? 'active' : ''}`}
            onClick={() => setMode('add-vendor')}
          >
            Add Vendor to Existing Item
          </button>
        </div>

        {mode === 'add-vendor' && (
          <div className="form-group">
            <label htmlFor="existing-item">Select Existing Item *</label>
            <select
              id="existing-item"
              value={selectedItem?.id || ''}
              onChange={(e) => {
                const item = existingItems.find(i => i.id === parseInt(e.target.value))
                if (item) handleItemSelect(item)
              }}
              required
            >
              <option value="">Select an item...</option>
              {(() => {
                // Group items by SKU to show unique SKUs
                const skuMap = new Map<string, Item[]>()
                existingItems.forEach(item => {
                  if (!skuMap.has(item.sku)) {
                    skuMap.set(item.sku, [])
                  }
                  skuMap.get(item.sku)!.push(item)
                })
                
                // Sort SKUs
                const sortedSkus = Array.from(skuMap.keys()).sort()
                
                return sortedSkus.flatMap(sku => {
                  const items = skuMap.get(sku)!
                  // If only one item with this SKU, show it directly
                  if (items.length === 1) {
                    const item = items[0]
                    return (
                      <option key={item.id} value={item.id}>
                        {item.sku} - {item.name} {item.vendor ? `(${item.vendor})` : ''}
                      </option>
                    )
                  }
                  // If multiple items with same SKU, show the first one as representative
                  // (user can still select any variant, but we'll use the first one to populate form)
                  const firstItem = items[0]
                  return (
                    <option key={firstItem.id} value={firstItem.id}>
                      {firstItem.sku} - {firstItem.name} ({items.length} vendor{items.length > 1 ? 's' : ''})
                    </option>
                  )
                })
              })()}
            </select>
            {selectedItem && (
              <div className="selected-item-info">
                <small>
                  Selected: <strong>{selectedItem.sku}</strong> - {selectedItem.name}
                  <br />
                  Existing vendors: {existingItems
                    .filter(i => i.sku === selectedItem.sku && i.vendor)
                    .map(i => i.vendor)
                    .join(', ') || 'None'}
                </small>
              </div>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="vendor">Vendor *</label>
              <select
                id="vendor"
                value={formData.vendor}
                onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
                required
                disabled={vendors.length === 0}
              >
                <option value="">
                  {vendors.length === 0 ? 'No approved vendors available' : 'Select Approved Vendor'}
                </option>
                {(() => {
                  // Filter out vendors that already have this SKU
                  if (mode === 'add-vendor' && formData.wwi_item_number) {
                    const existingVendors = existingItems
                      .filter(i => i.sku === formData.wwi_item_number && i.vendor)
                      .map(i => i.vendor)
                    return vendors
                      .filter(v => !existingVendors.includes(v.name))
                      .map((vendor) => (
                        <option key={vendor.id} value={vendor.name}>
                          {vendor.name}
                        </option>
                      ))
                  }
                  return vendors.map((vendor) => (
                    <option key={vendor.id} value={vendor.name}>
                      {vendor.name}
                    </option>
                  ))
                })()}
              </select>
              {mode === 'add-vendor' && formData.wwi_item_number && (() => {
                const existingVendors = existingItems
                  .filter(i => i.sku === formData.wwi_item_number && i.vendor)
                  .map(i => i.vendor)
                if (existingVendors.length > 0) {
                  return (
                    <small className="form-hint" style={{ color: '#3498db', marginTop: '0.5rem', display: 'block' }}>
                      Existing vendors for this item: {existingVendors.join(', ')}
                    </small>
                  )
                }
                return null
              })()}
              {vendors.length === 0 && (
                <small className="form-hint" style={{ color: '#e74c3c', marginTop: '0.5rem', display: 'block' }}>
                  Please approve vendors in the Quality tab before creating items.
                </small>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="vendor_item_number">Vendor Item Number</label>
              <input
                type="text"
                id="vendor_item_number"
                value={formData.vendor_item_number}
                onChange={(e) => setFormData({ ...formData, vendor_item_number: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label htmlFor="wwi_item_number">WWI Item Number (SKU) *</label>
              <input
                type="text"
                id="wwi_item_number"
                value={formData.wwi_item_number}
                onChange={(e) => setFormData({ ...formData, wwi_item_number: e.target.value })}
                required
                disabled={mode === 'add-vendor'}
              />
              {mode === 'add-vendor' && (
                <small className="form-hint">SKU is locked when adding vendor variant</small>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="name">Item Name *</label>
              <input
                type="text"
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                disabled={mode === 'add-vendor'}
              />
              {mode === 'add-vendor' && (
                <small className="form-hint">Name is locked when adding vendor variant</small>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                rows={3}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label htmlFor="item_type">Item Type *</label>
              <select
                id="item_type"
                value={formData.item_type}
                onChange={(e) => setFormData({ ...formData, item_type: e.target.value as any })}
                required
                disabled={mode === 'add-vendor'}
              >
                <option value="raw_material">Raw Material</option>
                <option value="distributed_item">Distributed Item</option>
                <option value="finished_good">Finished Good</option>
                <option value="indirect_material">Indirect Material</option>
              </select>
              {mode === 'add-vendor' && (
                <small className="form-hint">Item type is locked when adding vendor variant</small>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="pack_size">Pack Size</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  id="pack_size"
                  step="0.01"
                  min="0"
                  value={formData.pack_size}
                  onChange={(e) => setFormData({ ...formData, pack_size: e.target.value })}
                />
                <select
                  value={formData.unit_of_measure}
                  onChange={(e) => setFormData({ ...formData, unit_of_measure: e.target.value as 'lbs' | 'kg' | 'ea' })}
                >
                  <option value="lbs">lbs</option>
                  <option value="kg">kg</option>
                  <option value="ea">ea</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="price">Price</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  id="price"
                  step="0.01"
                  min="0"
                  value={formData.price}
                  onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                />
                <span className="unit-label">
                  per {formData.unit_of_measure}
                </span>
              </div>
              <small className="form-hint">Price per unit of measure</small>
            </div>
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-primary" 
              disabled={submitting || (mode === 'add-vendor' && !selectedItem)}
              onClick={(e) => {
                console.log('Button clicked', { submitting, formData })
                // Let the form handle submission
              }}
            >
              {submitting 
                ? (mode === 'add-vendor' ? 'Adding Vendor...' : 'Creating...') 
                : (mode === 'add-vendor' ? 'Add Vendor Variant' : 'Create Item')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateItemForm

