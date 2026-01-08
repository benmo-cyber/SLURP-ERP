import { useState, useEffect } from 'react'
import { createSalesOrder } from '../../api/salesOrders'
import { getItems } from '../../api/inventory'
import './CreateSalesOrder.css'

interface Item {
  id: number
  name: string
  unit_of_measure: string
}

interface SOItem {
  item_id: number | null
  vendor_part_number: string
  description: string
  quantity_ordered: number
  unit: string
  unit_price: number
  notes: string
}

interface CreateSalesOrderProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateSalesOrder({ onClose, onSuccess }: CreateSalesOrderProps) {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  
  const [formData, setFormData] = useState({
    customer_po_number: '',
    customer_name: '',
    customer_id: '',
    customer_address: '',
    customer_city: '',
    customer_state: '',
    customer_zip: '',
    customer_country: '',
    customer_phone: '',
    requested_ship_date: '',
    subtotal: 0,
    freight: 0,
    misc: 0,
    prepaid: 0,
    discount: 0,
    grand_total: 0,
    notes: '',
  })

  const [soItems, setSoItems] = useState<SOItem[]>([
    { item_id: null, vendor_part_number: '', description: '', quantity_ordered: 0, unit: '', unit_price: 0, notes: '' }
  ])

  useEffect(() => {
    loadItems()
  }, [])

  useEffect(() => {
    calculateTotals()
  }, [soItems, formData.freight, formData.misc, formData.prepaid, formData.discount])

  const loadItems = async () => {
    try {
      const data = await getItems()
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  const handleItemChange = (index: number, field: keyof SOItem, value: any) => {
    const updated = [...soItems]
    updated[index] = { ...updated[index], [field]: value }
    
    // Auto-populate description if item is selected
    if (field === 'item_id' && value) {
      const item = items.find(i => i.id === parseInt(value))
      if (item) {
        updated[index].description = item.name
        updated[index].unit = item.unit_of_measure
      }
    }
    
    setSoItems(updated)
  }

  const addItem = () => {
    setSoItems([...soItems, { item_id: null, vendor_part_number: '', description: '', quantity_ordered: 0, unit: '', unit_price: 0, notes: '' }])
  }

  const removeItem = (index: number) => {
    setSoItems(soItems.filter((_, i) => i !== index))
  }

  const convertUnit = (quantity: number, fromUnit: string, toUnit: string): number => {
    // Convert lbs to kg: 1 lb = 0.453592 kg
    // Convert kg to lbs: 1 kg = 2.20462 lbs
    if (fromUnit.toLowerCase() === 'lbs' && toUnit.toLowerCase() === 'kg') {
      return quantity * 0.453592
    } else if (fromUnit.toLowerCase() === 'kg' && toUnit.toLowerCase() === 'lbs') {
      return quantity * 2.20462
    }
    return quantity // Same unit or unknown conversion
  }

  const calculateTotals = () => {
    const subtotal = soItems.reduce((sum, item) => sum + (item.unit_price * item.quantity_ordered), 0)
    const grandTotal = subtotal + (formData.freight || 0) + (formData.misc || 0) - (formData.discount || 0) - (formData.prepaid || 0)
    
    setFormData(prev => ({
      ...prev,
      subtotal,
      grand_total: grandTotal
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.customer_name) {
      alert('Please enter customer name')
      return
    }

    if (soItems.length === 0 || soItems.some(item => !item.item_id || item.quantity_ordered <= 0)) {
      alert('Please add at least one item with valid quantity')
      return
    }

    try {
      setLoading(true)
      
      const payload = {
        customer_po_number: formData.customer_po_number || null,
        customer_name: formData.customer_name,
        customer_id: formData.customer_id || null,
        customer_address: formData.customer_address || null,
        customer_city: formData.customer_city || null,
        customer_state: formData.customer_state || null,
        customer_zip: formData.customer_zip || null,
        customer_country: formData.customer_country || null,
        customer_phone: formData.customer_phone || null,
        requested_ship_date: formData.requested_ship_date || null,
        subtotal: formData.subtotal,
        freight: formData.freight || 0,
        misc: formData.misc || 0,
        prepaid: formData.prepaid || 0,
        discount: formData.discount || 0,
        grand_total: formData.grand_total,
        notes: formData.notes || null,
        items: soItems.map(item => {
          // Convert quantity if needed
          const itemObj = items.find(i => i.id === item.item_id)
          let finalQuantity = item.quantity_ordered
          if (itemObj && item.unit && item.unit !== itemObj.unit_of_measure) {
            finalQuantity = convertUnit(item.quantity_ordered, item.unit, itemObj.unit_of_measure)
          }
          
          return {
            item_id: item.item_id,
            vendor_part_number: item.vendor_part_number || '',
            description: item.description,
            quantity_ordered: finalQuantity,
            unit_price: item.unit_price,
            notes: item.notes || '',
          }
        }),
        status: 'draft',
      }

      await createSalesOrder(payload)
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create sales order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to create sales order')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-so-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Sales Order from Customer PO</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="so-form-section">
            <h3>Customer Information</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Customer PO Number</label>
                <input
                  type="text"
                  value={formData.customer_po_number}
                  onChange={(e) => setFormData({ ...formData, customer_po_number: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Customer Name *</label>
                <input
                  type="text"
                  value={formData.customer_name}
                  onChange={(e) => setFormData({ ...formData, customer_name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Customer ID</label>
                <input
                  type="text"
                  value={formData.customer_id}
                  onChange={(e) => setFormData({ ...formData, customer_id: e.target.value })}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Address</label>
                <input
                  type="text"
                  value={formData.customer_address}
                  onChange={(e) => setFormData({ ...formData, customer_address: e.target.value })}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>City</label>
                <input
                  type="text"
                  value={formData.customer_city}
                  onChange={(e) => setFormData({ ...formData, customer_city: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>State</label>
                <input
                  type="text"
                  value={formData.customer_state}
                  onChange={(e) => setFormData({ ...formData, customer_state: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>ZIP</label>
                <input
                  type="text"
                  value={formData.customer_zip}
                  onChange={(e) => setFormData({ ...formData, customer_zip: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Country</label>
                <input
                  type="text"
                  value={formData.customer_country}
                  onChange={(e) => setFormData({ ...formData, customer_country: e.target.value })}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Phone</label>
                <input
                  type="text"
                  value={formData.customer_phone}
                  onChange={(e) => setFormData({ ...formData, customer_phone: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Requested Ship Date</label>
                <input
                  type="date"
                  value={formData.requested_ship_date}
                  onChange={(e) => setFormData({ ...formData, requested_ship_date: e.target.value })}
                />
              </div>
            </div>
          </div>

          <div className="so-form-section">
            <div className="section-header">
              <h3>Items</h3>
              <button type="button" onClick={addItem} className="btn btn-secondary">+ Add Item</button>
            </div>
            
            <table className="so-items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Vendor Part #</th>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit</th>
                  <th>Unit Price</th>
                  <th>Amount</th>
                  <th>Notes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {soItems.map((item, index) => (
                  <tr key={index}>
                    <td>
                      <select
                        value={item.item_id || ''}
                        onChange={(e) => handleItemChange(index, 'item_id', e.target.value ? parseInt(e.target.value) : null)}
                        required
                      >
                        <option value="">Select Item</option>
                        {items.map(i => (
                          <option key={i.id} value={i.id}>{i.name}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={item.vendor_part_number}
                        onChange={(e) => handleItemChange(index, 'vendor_part_number', e.target.value)}
                      />
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
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.quantity_ordered}
                        onChange={(e) => handleItemChange(index, 'quantity_ordered', parseFloat(e.target.value) || 0)}
                        className="number-input"
                        required
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={item.unit}
                        onChange={(e) => handleItemChange(index, 'unit', e.target.value)}
                        placeholder="lbs/kg"
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.unit_price}
                        onChange={(e) => handleItemChange(index, 'unit_price', parseFloat(e.target.value) || 0)}
                        className="number-input"
                        required
                      />
                    </td>
                    <td>${(item.unit_price * item.quantity_ordered).toFixed(2)}</td>
                    <td>
                      <input
                        type="text"
                        value={item.notes}
                        onChange={(e) => handleItemChange(index, 'notes', e.target.value)}
                      />
                    </td>
                    <td>
                      {soItems.length > 1 && (
                        <button type="button" onClick={() => removeItem(index)} className="btn btn-danger btn-sm">Remove</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Subtotal:</strong></td>
                  <td><strong>${formData.subtotal.toFixed(2)}</strong></td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Freight:</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.freight}
                      onChange={(e) => setFormData({ ...formData, freight: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Misc:</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.misc}
                      onChange={(e) => setFormData({ ...formData, misc: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Discount:</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.discount}
                      onChange={(e) => setFormData({ ...formData, discount: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Prepaid:</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.prepaid}
                      onChange={(e) => setFormData({ ...formData, prepaid: parseFloat(e.target.value) || 0 })}
                      className="number-input"
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Grand Total:</strong></td>
                  <td><strong>${formData.grand_total.toFixed(2)}</strong></td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="so-form-section">
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
              {loading ? 'Creating...' : 'Create Sales Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateSalesOrder



