import { useState, useEffect } from 'react'
import { createSalesOrder } from '../../api/salesOrders'
import { getItems } from '../../api/inventory'
import { getCustomers, getShipToLocations, getCustomerPricing } from '../../api/customers'
import { formatNumber, formatCurrency } from '../../utils/formatNumber'
import './CreateSalesOrder.css'

interface Item {
  id: number
  name: string
  unit_of_measure: string
}

interface CustomerPricing {
  id: number
  item: {
    id: number
    name: string
    sku?: string
    unit_of_measure?: string
  }
  item_id: number
  unit_price: number
  unit_of_measure: string
  effective_date: string
  expiry_date: string | null
  is_active: boolean
}

interface Customer {
  id: number
  name: string
}

interface ShipToLocation {
  id: number
  location_name: string
  address: string
  city: string
  state: string | null
  zip_code: string
  country: string
  phone: string | null
  contact_name: string | null
  email: string | null
  is_default?: boolean
}

interface SOItem {
  item_id: number | null
  vendor_part_number: string
  description: string
  quantity_ordered: number | string
  unit: string
  unit_price: number | string
  notes: string
}

interface CreateSalesOrderProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateSalesOrder({ onClose, onSuccess }: CreateSalesOrderProps) {
  const [items, setItems] = useState<Item[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [shipToLocations, setShipToLocations] = useState<ShipToLocation[]>([])
  const [customerPricing, setCustomerPricing] = useState<CustomerPricing[]>([])
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null)
  const [selectedShipToId, setSelectedShipToId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  
  const [formData, setFormData] = useState({
    customer_reference_number: '',
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
    { item_id: null, vendor_part_number: '', description: '', quantity_ordered: '', unit: '', unit_price: '', notes: '' }
  ])

  useEffect(() => {
    loadItems()
    loadCustomers()
  }, [])

  useEffect(() => {
    if (selectedCustomerId) {
      loadShipToLocations(selectedCustomerId)
      loadCustomerPricing(selectedCustomerId)
    } else {
      setShipToLocations([])
      setSelectedShipToId(null)
      setCustomerPricing([])
    }
  }, [selectedCustomerId])

  useEffect(() => {
    if (selectedShipToId && shipToLocations.length > 0) {
      const shipTo = shipToLocations.find(loc => loc.id === selectedShipToId)
      if (shipTo) {
        setFormData(prev => ({
          ...prev,
          customer_address: shipTo.address,
          customer_city: shipTo.city,
          customer_state: shipTo.state || '',
          customer_zip: shipTo.zip_code,
          customer_country: shipTo.country,
          customer_phone: shipTo.phone || '',
        }))
      }
    }
  }, [selectedShipToId, shipToLocations])

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

  const loadCustomers = async () => {
    try {
      const data = await getCustomers(true) // Only active customers
      setCustomers(data)
    } catch (error) {
      console.error('Failed to load customers:', error)
    }
  }

  const loadShipToLocations = async (customerId: number) => {
    try {
      const data = await getShipToLocations(customerId)
      setShipToLocations(data)
      // Auto-select default location if available
      const defaultLocation = data.find((loc: ShipToLocation) => loc.is_default)
      if (defaultLocation) {
        setSelectedShipToId(defaultLocation.id)
      } else if (data.length > 0) {
        setSelectedShipToId(data[0].id)
      } else {
        setSelectedShipToId(null)
      }
    } catch (error) {
      console.error('Failed to load ship-to locations:', error)
      setShipToLocations([])
    }
  }

  const loadCustomerPricing = async (customerId: number) => {
    try {
      const data = await getCustomerPricing(customerId)
      
      // Handle both array and paginated response
      const pricingList = Array.isArray(data) ? data : (data.results || [])
      
      // Filter to only active pricing that is currently effective
      const today = new Date().toISOString().split('T')[0]
      const activePricing = pricingList.filter((pricing: any) => {
        if (!pricing.is_active) return false
        if (pricing.effective_date > today) return false
        if (pricing.expiry_date && pricing.expiry_date < today) return false
        return true
      })
      
      // If multiple pricing records for same item, get the most recent effective one
      const pricingMap = new Map<number, CustomerPricing>()
      activePricing.forEach((pricing: any) => {
        const itemId = pricing.item_id || pricing.item?.id
        if (!itemId) {
          console.warn('Pricing record missing item_id:', pricing)
          return
        }
        const existing = pricingMap.get(itemId)
        if (!existing || pricing.effective_date > existing.effective_date) {
          // Ensure item object is properly structured
          const item = pricing.item || {}
          pricingMap.set(itemId, {
            id: pricing.id,
            item: {
              id: itemId,
              name: item.name || 'Unknown Item',
              sku: item.sku,
              unit_of_measure: item.unit_of_measure || pricing.unit_of_measure
            },
            item_id: itemId,
            unit_price: pricing.unit_price,
            unit_of_measure: pricing.unit_of_measure,
            effective_date: pricing.effective_date,
            expiry_date: pricing.expiry_date,
            is_active: pricing.is_active
          })
        }
      })
      
      const finalPricing = Array.from(pricingMap.values())
      setCustomerPricing(finalPricing)
    } catch (error) {
      console.error('Failed to load customer pricing:', error)
      setCustomerPricing([])
    }
  }

  const handleCustomerChange = (customerId: string) => {
    const id = customerId ? parseInt(customerId) : null
    setSelectedCustomerId(id)
    const customer = customers.find(c => c.id === id)
    if (customer) {
      setFormData(prev => ({ ...prev, customer_name: customer.name }))
    } else {
      setFormData(prev => ({ ...prev, customer_name: '' }))
    }
    // Clear ship-to selection when customer changes
    setSelectedShipToId(null)
    setFormData(prev => ({
      ...prev,
      customer_address: '',
      customer_city: '',
      customer_state: '',
      customer_zip: '',
      customer_country: '',
      customer_phone: '',
    }))
    // Clear all items when customer changes
    setSoItems([{ item_id: null, vendor_part_number: '', description: '', quantity_ordered: '', unit: '', unit_price: '', notes: '' }])
  }

  const handleItemChange = (index: number, field: keyof SOItem, value: any) => {
    const updated = [...soItems]
    updated[index] = { ...updated[index], [field]: value }
    
      // Auto-populate description, unit, and price from customer pricing when item is selected
    if (field === 'item_id' && value) {
      const itemId = typeof value === 'number' ? value : parseInt(value)
      const pricing = customerPricing.find(p => p.item_id === itemId)
      if (pricing && pricing.item) {
        updated[index].description = pricing.item.name || ''
        updated[index].unit = pricing.unit_of_measure
        updated[index].unit_price = pricing.unit_price
      } else {
        // Fallback to item data if pricing not found (shouldn't happen if filtering works)
        const item = items.find(i => i.id === itemId)
        if (item) {
          updated[index].description = item.name
          updated[index].unit = item.unit_of_measure
        }
      }
    }
    
    // Handle quantity and price fields - allow empty string
    if (field === 'quantity_ordered' || field === 'unit_price') {
      if (value === '' || value === null || value === undefined) {
        updated[index][field] = ''
      } else {
        const numValue = typeof value === 'string' ? parseFloat(value) : value
        updated[index][field] = isNaN(numValue) ? '' : numValue
      }
    }
    
    setSoItems(updated)
  }

  const addItem = () => {
    setSoItems([...soItems, { item_id: null, vendor_part_number: '', description: '', quantity_ordered: '', unit: '', unit_price: '', notes: '' }])
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
    const subtotal = soItems.reduce((sum, item) => {
      const price = typeof item.unit_price === 'string' ? parseFloat(item.unit_price) || 0 : item.unit_price
      const qty = typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) || 0 : item.quantity_ordered
      return sum + (price * qty)
    }, 0)
    const grandTotal = subtotal + (formData.freight || 0) + (formData.misc || 0) - (formData.discount || 0) - (formData.prepaid || 0)
    
    setFormData(prev => ({
      ...prev,
      subtotal,
      grand_total: grandTotal
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!selectedCustomerId) {
      alert('Please select a customer')
      return
    }

    if (!selectedShipToId) {
      alert('Please select a ship-to location')
      return
    }

    if (soItems.length === 0 || soItems.some(item => {
      if (!item.item_id) return true
      const qty = typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) : item.quantity_ordered
      return !qty || qty <= 0
    })) {
      alert('Please add at least one item with valid quantity')
      return
    }

    try {
      setLoading(true)
      
      const payload = {
        customer: selectedCustomerId,
        ship_to_location: selectedShipToId,
        customer_reference_number: formData.customer_reference_number || null,
        customer_name: formData.customer_name,
        customer_id: formData.customer_id || null, // This is the Customer PO Number field
        customer_address: formData.customer_address || null,
        customer_city: formData.customer_city || null,
        customer_state: formData.customer_state || null,
        customer_zip: formData.customer_zip || null,
        customer_country: formData.customer_country || null,
        customer_phone: formData.customer_phone || null,
        expected_ship_date: formData.requested_ship_date || null,
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
          let finalQuantity = typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) || 0 : item.quantity_ordered
          const unitPrice = typeof item.unit_price === 'string' ? parseFloat(item.unit_price) || 0 : item.unit_price
          
          if (itemObj && item.unit && item.unit !== itemObj.unit_of_measure) {
            finalQuantity = convertUnit(finalQuantity, item.unit, itemObj.unit_of_measure)
          }
          
          return {
            item_id: item.item_id,
            vendor_part_number: item.vendor_part_number || '',
            description: item.description,
            quantity_ordered: finalQuantity,
            unit_price: unitPrice,
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
                <label>Customer Reference Number (Optional)</label>
                <input
                  type="text"
                  value={formData.customer_reference_number}
                  onChange={(e) => setFormData({ ...formData, customer_reference_number: e.target.value })}
                  placeholder="Defaults to Customer PO Number if not provided"
                />
                <small style={{ color: '#666', fontSize: '0.85rem' }}>
                  If not provided, Customer PO Number will be used as reference
                </small>
              </div>
              <div className="form-group">
                <label>Customer Name *</label>
                <select
                  value={selectedCustomerId || ''}
                  onChange={(e) => handleCustomerChange(e.target.value)}
                  required
                >
                  <option value="">Select Customer</option>
                  {customers.map(customer => (
                    <option key={customer.id} value={customer.id}>{customer.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Customer PO Number</label>
                <input
                  type="text"
                  value={formData.customer_id}
                  onChange={(e) => setFormData({ ...formData, customer_id: e.target.value })}
                  placeholder="Used as reference if Customer Reference Number not provided"
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Ship-to *</label>
                <select
                  value={selectedShipToId || ''}
                  onChange={(e) => setSelectedShipToId(e.target.value ? parseInt(e.target.value) : null)}
                  required
                  disabled={!selectedCustomerId}
                >
                  <option value="">{selectedCustomerId ? 'Select Ship-to Location' : 'Select Customer First'}</option>
                  {shipToLocations.map(location => (
                    <option key={location.id} value={location.id}>
                      {location.location_name}
                    </option>
                  ))}
                </select>
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
                        value={item.item_id ? String(item.item_id) : ''}
                        onChange={(e) => handleItemChange(index, 'item_id', e.target.value ? parseInt(e.target.value) : null)}
                        required
                        disabled={!selectedCustomerId}
                      >
                        <option value="">
                          {selectedCustomerId ? (customerPricing.length === 0 ? 'No items with pricing' : 'Select Item') : 'Select Customer First'}
                        </option>
                        {selectedCustomerId && customerPricing.length > 0 && customerPricing.map(pricing => (
                          <option key={pricing.item_id} value={String(pricing.item_id)}>
                            {pricing.item.name} {pricing.item.sku ? `(${pricing.item.sku})` : ''}
                          </option>
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
                        value={item.quantity_ordered === '' ? '' : item.quantity_ordered}
                        onChange={(e) => handleItemChange(index, 'quantity_ordered', e.target.value)}
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
                        value={item.unit_price === '' ? '' : item.unit_price}
                        onChange={(e) => handleItemChange(index, 'unit_price', e.target.value)}
                        className="number-input"
                        required
                      />
                    </td>
                    <td>{formatCurrency((typeof item.unit_price === 'string' ? parseFloat(item.unit_price) || 0 : item.unit_price) * (typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) || 0 : item.quantity_ordered))}</td>
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
                  <td><strong>{formatCurrency(formData.subtotal)}</strong></td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Freight:</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.freight || ''}
                      onChange={(e) => setFormData({ ...formData, freight: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
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
                      value={formData.misc || ''}
                      onChange={(e) => setFormData({ ...formData, misc: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
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
                      value={formData.discount || ''}
                      onChange={(e) => setFormData({ ...formData, discount: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
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
                      value={formData.prepaid || ''}
                      onChange={(e) => setFormData({ ...formData, prepaid: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
                      className="number-input"
                    />
                  </td>
                  <td colSpan={2}></td>
                </tr>
                <tr>
                  <td colSpan={6} className="text-right"><strong>Grand Total:</strong></td>
                  <td><strong>{formatCurrency(formData.grand_total)}</strong></td>
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



