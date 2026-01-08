import { useState, useEffect } from 'react'
import { createPurchaseOrder } from '../../api/purchaseOrders'
import { getVendors } from '../../api/quality'
import { getItems } from '../../api/inventory'
import { getCostMasterByProductCode } from '../../api/costMaster'
import './CreatePurchaseOrder.css'

interface Vendor {
  id: number
  name: string
  address?: string
}

interface Item {
  id: number
  name: string
  sku: string
  unit_of_measure: string
  price?: number
  pack_size?: number
}

interface POItem {
  item_id: number | null
  description: string
  unit_cost: number
  unit_of_measure: string
  quantity: number
  notes: string
  original_unit?: string // Store the item's original unit
  costMasterData?: any // Store cost master data for recalculation
}

interface CreatePurchaseOrderProps {
  onClose: () => void
  onSuccess: () => void
}

function CreatePurchaseOrder({ onClose, onSuccess }: CreatePurchaseOrderProps) {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  
  const [formData, setFormData] = useState({
    order_number: '',
    vendor_id: '',
    required_date: '',
    expected_delivery_date: '',
    shipping_terms: '',
    shipping_method: '',
    ship_to_name: 'Wildwood Ingredients, LLC',
    ship_to_address: '6431 Michels Dr.',
    ship_to_city: 'Washington',
    ship_to_state: 'MO',
    ship_to_zip: '63090',
    ship_to_country: 'USA',
    vendor_address: '',
    vendor_city: '',
    vendor_state: '',
    vendor_zip: '',
    vendor_country: '',
    coa_sds_email: '',
    discount: 0,
    shipping_cost: 0,
    notes: '',
  })

  const [poItems, setPoItems] = useState<POItem[]>([
    { item_id: null, description: '', unit_cost: 0, unit_of_measure: '', quantity: 0, notes: '', original_unit: '', costMasterData: null }
  ])

  useEffect(() => {
    loadVendors()
    loadItems()
  }, [])

  const loadVendors = async () => {
    try {
      const data = await getVendors()
      setVendors(data)
    } catch (error) {
      console.error('Failed to load vendors:', error)
    }
  }

  const loadItems = async () => {
    try {
      // Only load items from approved vendors
      const data = await getItems(true)
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  const handleVendorChange = (vendorId: string) => {
    setFormData({ ...formData, vendor_id: vendorId })
    if (vendorId) {
      const vendor = vendors.find(v => v.id === parseInt(vendorId))
      if (vendor && vendor.address) {
        setFormData(prev => ({ ...prev, vendor_address: vendor.address || '' }))
      }
    }
  }

  const handleItemChange = async (index: number, field: keyof POItem, value: any) => {
    // If changing item_id, we need to handle async price loading
    if (field === 'item_id') {
      const updated = [...poItems]
      
      if (value) {
        const itemId = typeof value === 'string' ? parseInt(value) : value
        const item = items.find(i => i.id === itemId)
        
        if (item) {
          // Store original unit
          const originalUnit = item.unit_of_measure
          
          // Update description and unit of measure immediately
          updated[index] = { 
            ...updated[index], 
            item_id: itemId,
            description: item.name,
            unit_of_measure: originalUnit,
            original_unit: originalUnit
          }
          setPoItems(updated)
          
          // Then load pricing asynchronously
          let priceToSet = 0
          let priceSet = false
          let costMasterData = null
          
          // Pull pricing from CostMaster first
          if (item.sku) {
            try {
              const costMaster = await getCostMasterByProductCode(item.sku)
              if (costMaster) {
                costMasterData = costMaster
                // Use price based on item's unit of measure
                if (originalUnit === 'lbs' && costMaster.price_per_lb) {
                  priceToSet = costMaster.price_per_lb
                  priceSet = true
                } else if (originalUnit === 'kg' && costMaster.price_per_kg) {
                  priceToSet = costMaster.price_per_kg
                  priceSet = true
                } else if (originalUnit === 'lbs' && costMaster.price_per_kg) {
                  // Convert kg to lbs
                  priceToSet = costMaster.price_per_kg / 2.20462
                  priceSet = true
                } else if (originalUnit === 'kg' && costMaster.price_per_lb) {
                  // Convert lbs to kg
                  priceToSet = costMaster.price_per_lb * 2.20462
                  priceSet = true
                }
              }
            } catch (error) {
              console.error('Failed to load cost master:', error)
            }
          }
          
          // Fall back to item's price field if CostMaster doesn't have pricing
          if (!priceSet && item.price) {
            priceToSet = item.price
            priceSet = true
          }
          
          // Update price if we found one
          if (priceSet) {
            const finalUpdated = [...poItems]
            finalUpdated[index] = { 
              ...finalUpdated[index], 
              item_id: itemId,
              description: item.name,
              unit_of_measure: originalUnit,
              original_unit: originalUnit,
              unit_cost: priceToSet,
              costMasterData: costMasterData
            }
            setPoItems(finalUpdated)
          } else {
            // Even if no price, store the cost master data if we have it
            if (costMasterData) {
              const finalUpdated = [...poItems]
              finalUpdated[index] = { 
                ...finalUpdated[index], 
                costMasterData: costMasterData
              }
              setPoItems(finalUpdated)
            }
          }
        }
      } else {
        // Clearing the selection
        updated[index] = { 
          ...updated[index], 
          item_id: null,
          description: '',
          unit_of_measure: '',
          unit_cost: 0,
          original_unit: '',
          costMasterData: null
        }
        setPoItems(updated)
      }
    } else if (field === 'unit_of_measure') {
      // When unit of measure changes, recalculate unit cost
      const updated = [...poItems]
      const currentItem = { ...updated[index] }
      const newUnit = value
      const oldUnit = currentItem.unit_of_measure
      
      console.log('Unit change:', { index, oldUnit, newUnit, currentCost: currentItem.unit_cost, hasCostMaster: !!currentItem.costMasterData, itemId: currentItem.item_id })
      
      // Only allow toggle for lbs/kg items
      if (currentItem.item_id && (oldUnit === 'lbs' || oldUnit === 'kg') && (newUnit === 'lbs' || newUnit === 'kg')) {
        let newPrice = currentItem.unit_cost
        
        // Recalculate unit cost based on cost master data
        if (currentItem.costMasterData) {
          const costMaster = currentItem.costMasterData
          
          if (newUnit === 'lbs' && costMaster.price_per_lb) {
            newPrice = costMaster.price_per_lb
          } else if (newUnit === 'kg' && costMaster.price_per_kg) {
            newPrice = costMaster.price_per_kg
          } else if (newUnit === 'lbs' && costMaster.price_per_kg) {
            // Convert kg to lbs
            newPrice = costMaster.price_per_kg / 2.20462
          } else if (newUnit === 'kg' && costMaster.price_per_lb) {
            // Convert lbs to kg
            newPrice = costMaster.price_per_lb * 2.20462
          } else {
            // Fallback: convert from current price
            if (oldUnit === 'lbs' && newUnit === 'kg') {
              newPrice = currentItem.unit_cost * 2.20462
            } else if (oldUnit === 'kg' && newUnit === 'lbs') {
              newPrice = currentItem.unit_cost / 2.20462
            }
          }
        } else {
          // No cost master data, convert the current price
          if (oldUnit === 'lbs' && newUnit === 'kg') {
            newPrice = currentItem.unit_cost * 2.20462
          } else if (oldUnit === 'kg' && newUnit === 'lbs') {
            newPrice = currentItem.unit_cost / 2.20462
          }
        }
        
        console.log('New price calculated:', newPrice)
        
        updated[index] = {
          ...currentItem,
          unit_of_measure: newUnit,
          unit_cost: newPrice
        }
        
        setPoItems(updated)
      } else {
        // For 'ea' or other units, just update the unit
        updated[index] = { ...currentItem, unit_of_measure: value }
        setPoItems(updated)
      }
    } else {
      // For other fields, update immediately
      const updated = [...poItems]
      updated[index] = { ...updated[index], [field]: value }
      setPoItems(updated)
    }
  }

  const addItem = () => {
    setPoItems([...poItems, { item_id: null, description: '', unit_cost: 0, unit_of_measure: '', quantity: 0, notes: '', original_unit: '', costMasterData: null }])
  }

  const removeItem = (index: number) => {
    setPoItems(poItems.filter((_, i) => i !== index))
  }

  const calculateSubtotal = () => {
    return poItems.reduce((sum, item) => sum + (item.unit_cost * item.quantity), 0)
  }

  const calculateTotal = () => {
    const subtotal = calculateSubtotal()
    const discount = formData.discount || 0
    const shipping = formData.shipping_cost || 0
    return subtotal - discount + shipping
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.vendor_id) {
      alert('Please select a vendor')
      return
    }

    if (poItems.length === 0 || poItems.some(item => !item.item_id || item.quantity <= 0)) {
      alert('Please add at least one item with valid quantity')
      return
    }

    try {
      setLoading(true)
      
      const payload = {
        ...formData,
        vendor_id: parseInt(formData.vendor_id),
        order_number: formData.order_number || null, // null for auto-generation
        // Set required_date from expected_delivery_date if not provided
        required_date: formData.required_date || formData.expected_delivery_date || null,
        expected_delivery_date: formData.expected_delivery_date || formData.required_date || null,
        items: poItems.map(item => ({
          item_id: item.item_id,
          description: item.description,
          unit_cost: item.unit_cost,
          quantity: item.quantity,
          notes: item.notes || '',
        })),
        discount: formData.discount || 0,
        shipping_cost: formData.shipping_cost || 0,
        status: 'draft',
      }

      await createPurchaseOrder(payload)
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create purchase order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to create purchase order')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-po-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Purchase Order</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="po-form-section">
            <div className="po-header">
              <h2>PURCHASE ORDER</h2>
              <div className="po-header-info">
                <div className="form-group">
                  <label>Date</label>
                  <input
                    type="date"
                    value={new Date().toISOString().split('T')[0]}
                    readOnly
                  />
                </div>
                <div className="form-group">
                  <label>Order # (leave blank for auto-generation)</label>
                  <input
                    type="text"
                    value={formData.order_number}
                    onChange={(e) => setFormData({ ...formData, order_number: e.target.value })}
                    placeholder="00001"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="po-form-section">
            <div className="vendor-ship-to-container">
              <div className="vendor-section">
                <h3>Vendor</h3>
                <div className="form-group">
                  <label>Vendor *</label>
                  <select
                    value={formData.vendor_id}
                    onChange={(e) => handleVendorChange(e.target.value)}
                    required
                  >
                    <option value="">Select Vendor</option>
                    {vendors.map(vendor => (
                      <option key={vendor.id} value={vendor.id}>{vendor.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Address</label>
                  <input
                    type="text"
                    value={formData.vendor_address}
                    onChange={(e) => setFormData({ ...formData, vendor_address: e.target.value })}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.vendor_city}
                      onChange={(e) => setFormData({ ...formData, vendor_city: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.vendor_state}
                      onChange={(e) => setFormData({ ...formData, vendor_state: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>ZIP</label>
                    <input
                      type="text"
                      value={formData.vendor_zip}
                      onChange={(e) => setFormData({ ...formData, vendor_zip: e.target.value })}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Country</label>
                  <input
                    type="text"
                    value={formData.vendor_country}
                    onChange={(e) => setFormData({ ...formData, vendor_country: e.target.value })}
                  />
                </div>
              </div>

              <div className="ship-to-section">
                <h3>Ship to</h3>
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={formData.ship_to_name}
                    onChange={(e) => setFormData({ ...formData, ship_to_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Address</label>
                  <input
                    type="text"
                    value={formData.ship_to_address}
                    onChange={(e) => setFormData({ ...formData, ship_to_address: e.target.value })}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.ship_to_city}
                      onChange={(e) => setFormData({ ...formData, ship_to_city: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.ship_to_state}
                      onChange={(e) => setFormData({ ...formData, ship_to_state: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>ZIP</label>
                    <input
                      type="text"
                      value={formData.ship_to_zip}
                      onChange={(e) => setFormData({ ...formData, ship_to_zip: e.target.value })}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Country</label>
                  <input
                    type="text"
                    value={formData.ship_to_country}
                    onChange={(e) => setFormData({ ...formData, ship_to_country: e.target.value })}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="po-form-section">
            <div className="form-row">
              <div className="form-group">
                <label>Shipping Terms</label>
                <input
                  type="text"
                  value={formData.shipping_terms}
                  onChange={(e) => setFormData({ ...formData, shipping_terms: e.target.value })}
                  placeholder="CIF Chicago"
                  required
                />
                <small className="required-hint">* Required</small>
              </div>
              <div className="form-group">
                <label>Shipping Method</label>
                <input
                  type="text"
                  value={formData.shipping_method}
                  onChange={(e) => setFormData({ ...formData, shipping_method: e.target.value })}
                  placeholder="Air Freight"
                  required
                />
                <small className="required-hint">* Required</small>
              </div>
              <div className="form-group">
                <label>Delivery Date *</label>
                <input
                  type="date"
                  value={formData.expected_delivery_date}
                  onChange={(e) => {
                    const deliveryDate = e.target.value
                    // Set both required_date and expected_delivery_date from Delivery Date
                    setFormData({ 
                      ...formData, 
                      expected_delivery_date: deliveryDate,
                      required_date: deliveryDate // Required date matches delivery date
                    })
                  }}
                  required
                />
              </div>
            </div>
          </div>

          <div className="po-form-section">
            <div className="section-header">
              <h3>Items</h3>
              <button type="button" onClick={addItem} className="btn btn-secondary">+ Add Item</button>
            </div>
            
            <table className="po-items-table">
              <thead>
                <tr>
                  <th>Item #</th>
                  <th>Description</th>
                  <th>Unit of Measure</th>
                  <th>Unit Cost</th>
                  <th>Qty</th>
                  <th>Amount</th>
                  <th>Notes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {poItems.map((item, index) => (
                  <tr key={index}>
                    <td>
                      <select
                        value={item.item_id ? String(item.item_id) : ''}
                        onChange={(e) => {
                          const selectedValue = e.target.value
                          console.log('Item selected:', selectedValue, 'Items available:', items.length)
                          handleItemChange(index, 'item_id', selectedValue || null)
                        }}
                        required
                        className="item-select"
                      >
                        <option value="">Select Item</option>
                        {items.length === 0 ? (
                          <option disabled>No items available</option>
                        ) : (
                          items.map(i => (
                            <option key={i.id} value={String(i.id)}>{i.sku} - {i.name}</option>
                          ))
                        )}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={item.description}
                        onChange={(e) => handleItemChange(index, 'description', e.target.value)}
                        required
                      />
                    </td>
                    <td>
                      {item.item_id && item.unit_of_measure && (item.unit_of_measure === 'lbs' || item.unit_of_measure === 'kg') ? (
                        <div className="unit-toggle-group">
                          <button
                            type="button"
                            className={`unit-toggle-btn ${item.unit_of_measure === 'lbs' ? 'active' : ''}`}
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              console.log('Toggling to lbs, current:', item.unit_of_measure, 'cost:', item.unit_cost)
                              handleItemChange(index, 'unit_of_measure', 'lbs')
                            }}
                          >
                            lbs
                          </button>
                          <button
                            type="button"
                            className={`unit-toggle-btn ${item.unit_of_measure === 'kg' ? 'active' : ''}`}
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              console.log('Toggling to kg, current:', item.unit_of_measure, 'cost:', item.unit_cost)
                              handleItemChange(index, 'unit_of_measure', 'kg')
                            }}
                          >
                            kg
                          </button>
                        </div>
                      ) : item.unit_of_measure ? (
                        <input
                          type="text"
                          value={item.unit_of_measure || ''}
                          readOnly
                          className="read-only-input"
                        />
                      ) : (
                        <span>-</span>
                      )}
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.unit_cost}
                        readOnly
                        className="number-input read-only-input"
                      />
                    </td>
                    <td>
                      <div className="quantity-input-wrapper">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.quantity}
                          onChange={(e) => handleItemChange(index, 'quantity', parseFloat(e.target.value) || 0)}
                          className="number-input"
                          required
                        />
                      </div>
                    </td>
                    <td>${(item.unit_cost * item.quantity).toFixed(2)}</td>
                    <td>
                      <input
                        type="text"
                        value={item.notes}
                        onChange={(e) => handleItemChange(index, 'notes', e.target.value)}
                      />
                    </td>
                    <td>
                      {poItems.length > 1 && (
                        <button type="button" onClick={() => removeItem(index)} className="btn btn-danger btn-sm">Remove</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={4} className="text-right"><strong>SUBTOTAL</strong></td>
                  <td><strong>${calculateSubtotal().toFixed(2)}</strong></td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={4} className="text-right"><strong>DISCOUNT</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.discount}
                      onChange={(e) => setFormData({ ...formData, discount: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                      style={{ width: '100px', textAlign: 'right' }}
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={4} className="text-right"><strong>SHIPPING</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.shipping_cost}
                      onChange={(e) => setFormData({ ...formData, shipping_cost: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                      style={{ width: '100px', textAlign: 'right' }}
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={4} className="text-right"><strong>TOTAL</strong></td>
                  <td><strong>${calculateTotal().toFixed(2)}</strong></td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="po-form-section">
            <div className="form-group">
              <label>Please email CoA, SDS and shipping documents to</label>
              <input
                type="email"
                value={formData.coa_sds_email}
                onChange={(e) => setFormData({ ...formData, coa_sds_email: e.target.value })}
                placeholder="Gary.morris@wildwoodingredients.com"
              />
            </div>
            <div className="form-group">
              <label>Notes</label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={3}
              />
            </div>
          </div>

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary" disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Creating...' : 'Create PO (Draft)'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreatePurchaseOrder


