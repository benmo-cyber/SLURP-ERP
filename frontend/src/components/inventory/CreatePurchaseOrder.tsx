import { useState, useEffect, useMemo } from 'react'
import { createPurchaseOrder } from '../../api/purchaseOrders'
import { getVendors } from '../../api/quality'
import { getItems } from '../../api/inventory'
import { getCostMasterByProductCode } from '../../api/costMaster'
import { formatCurrency } from '../../utils/formatNumber'
import './CreatePurchaseOrder.css'

interface Vendor {
  id: number
  name: string
  address?: string
  vendor_id?: string
  contact_name?: string
  email?: string
  phone?: string
  approval_status?: string
}

interface Item {
  id: number
  name: string
  sku: string
  unit_of_measure: string
  price?: number
  pack_size?: number
  vendor_item_name?: string
  display_name_for_vendor?: string
}

interface POItem {
  item_id: number | null
  sku: string | null  // Selected SKU
  vendor: string | null  // Selected vendor for this SKU
  description: string
  unit_cost: number | string
  unit_of_measure: string
  quantity: number | string
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
  const [loadingVendors, setLoadingVendors] = useState(true)
  
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
    { item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }
  ])

  useEffect(() => {
    loadVendors()
    loadItems()
  }, [])

  // Memoize vendor options to prevent unnecessary re-renders
  const vendorOptions = useMemo(() => {
    return vendors.map(vendor => ({
      id: vendor.id,
      name: vendor.name,
      value: String(vendor.id)
    }))
  }, [vendors])


  const loadVendors = async () => {
    try {
      setLoadingVendors(true)
      const data = await getVendors()
      const vendorsList = Array.isArray(data) ? data : []
      setVendors(vendorsList)
      if (vendorsList.length === 0) {
        console.warn('No vendors found in the system')
      }
    } catch (error: any) {
      console.error('Failed to load vendors:', error)
      alert(`Failed to load vendors: ${error.response?.data?.detail || error.message || 'Unknown error'}`)
      setVendors([])
    } finally {
      setLoadingVendors(false)
    }
  }

  const loadItems = async () => {
    try {
      // Load all items to get unique SKUs and vendors
      const data = await getItems(true)
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  // Get items filtered by selected vendor
  const getFilteredItems = () => {
    if (!formData.vendor_id) {
      return items
    }
    
    const selectedVendor = vendors.find(v => String(v.id) === formData.vendor_id)
    if (!selectedVendor) {
      return items
    }
    
    // Filter items to only show items where the item's vendor matches the selected vendor
    return items.filter(item => {
      const itemVendor = (item as any).vendor || ''
      return itemVendor === selectedVendor.name
    })
  }

  // Get unique SKUs from items (filtered by selected vendor)
  const getUniqueSkus = () => {
    const filteredItems = getFilteredItems()
    const skuSet = new Set<string>()
    filteredItems.forEach(item => {
      if (item.sku) {
        skuSet.add(item.sku)
      }
    })
    return Array.from(skuSet).sort()
  }

  // Get vendors for a specific SKU (should only be the selected vendor)
  const getVendorsForSku = (sku: string) => {
    const filteredItems = getFilteredItems()
    return filteredItems
      .filter(item => item.sku === sku)
      .map(item => ({
        id: item.id,
        vendor: (item as any).vendor || 'Unknown',
        name: item.name,
        unit_of_measure: item.unit_of_measure,
        price: item.price,
        pack_size: item.pack_size
      }))
      .filter((item, index, self) => 
        index === self.findIndex(i => i.vendor === item.vendor)
      )
  }

  const handleVendorChange = (vendorId: string) => {
    // Ensure vendorId is a string and normalize it
    const vendorIdStr = vendorId ? String(vendorId).trim() : ''
    
    if (vendorIdStr) {
      const vendor = vendors.find(v => String(v.id) === vendorIdStr)
      
      if (vendor) {
        // Update vendor address fields if available - use structured fields if available, fallback to legacy address
        setFormData(prev => ({ 
          ...prev, 
          vendor_id: vendorIdStr,
          vendor_address: vendor.street_address || vendor.address || prev.vendor_address || '',
          vendor_city: vendor.city || prev.vendor_city || '',
          vendor_state: vendor.state || prev.vendor_state || '',
          vendor_zip: vendor.zip_code || prev.vendor_zip || '',
          vendor_country: vendor.country || prev.vendor_country || 'USA'
        }))
        
        // Clear all PO items when vendor changes since items are vendor-specific
        setPoItems([{ item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }])
      } else {
        // Vendor not found, just update the ID
        setFormData(prev => ({ ...prev, vendor_id: vendorIdStr }))
        // Clear items when vendor changes
        setPoItems([{ item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }])
      }
    } else {
      // Clear vendor address when no vendor selected
      setFormData(prev => ({ 
        ...prev, 
        vendor_id: '',
        vendor_address: '',
        vendor_city: '',
        vendor_state: '',
        vendor_zip: '',
        vendor_country: ''
      }))
      // Clear items when vendor is cleared
      setPoItems([{ item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }])
    }
  }

  const handleItemChange = async (index: number, field: keyof POItem, value: any) => {
    // Handle SKU selection
    if (field === 'sku') {
      const updated = [...poItems]
      const selectedVendor = vendors.find(v => String(v.id) === formData.vendor_id)
      const vendorName = selectedVendor?.name || ''
      
      updated[index] = { 
        ...updated[index], 
        sku: value || null,
        vendor: vendorName || null, // Auto-set vendor from form selection
        item_id: null, // Reset item_id
        description: '',
        unit_cost: '',
        unit_of_measure: '',
        costMasterData: null
      }
      setPoItems(updated)
      
      // If SKU and vendor are set, try to find and load the item
      if (value && vendorName) {
        const filteredItems = getFilteredItems()
        const matchingItem = filteredItems.find(i => 
          i.sku === value && 
          ((i as any).vendor === vendorName || (!(i as any).vendor && vendorName === 'Unknown'))
        )
        
        if (matchingItem) {
          // Use vendor_item_name if available, otherwise use name (WWI name)
          const displayName = (matchingItem as any).display_name_for_vendor || matchingItem.vendor_item_name || matchingItem.name
          updated[index] = {
            ...updated[index],
            item_id: matchingItem.id,
            description: displayName,
            unit_of_measure: matchingItem.unit_of_measure,
            original_unit: matchingItem.unit_of_measure
          }
          setPoItems(updated)
          await loadItemPricing(index, matchingItem, vendorName)
        }
      }
      return
    }
    
    // Handle vendor selection for a SKU (auto-set from form vendor, not user-selectable)
    if (field === 'vendor') {
      // Vendor is automatically set from the form vendor selection, so this shouldn't be called
      // But if it is, use the selected vendor from the form
      const updated = [...poItems]
      const currentItem = updated[index]
      const selectedVendor = vendors.find(v => String(v.id) === formData.vendor_id)
      const vendorName = selectedVendor?.name || value || ''
      
      if (currentItem.sku && vendorName) {
        // Find the item matching SKU + vendor (must match the selected vendor)
        const filteredItems = getFilteredItems()
        const matchingItem = filteredItems.find(i => 
          i.sku === currentItem.sku && 
          ((i as any).vendor === vendorName || (!(i as any).vendor && vendorName === 'Unknown'))
        )
        
        if (matchingItem) {
          // Use vendor_item_name if available, otherwise use name (WWI name)
          const displayName = (matchingItem as any).display_name_for_vendor || matchingItem.vendor_item_name || matchingItem.name
          // Update with the matching item - use the selected vendor name
          const vendorValue = String(vendorName).trim()
          updated[index] = { 
            ...updated[index], 
            vendor: vendorValue,
            item_id: matchingItem.id,
            description: displayName,
            unit_of_measure: matchingItem.unit_of_measure,
            original_unit: matchingItem.unit_of_measure
          }
          setPoItems(updated)
          
          // Load pricing asynchronously - use functional update to preserve vendor
          await loadItemPricing(index, matchingItem, vendorValue)
        } else {
          // Item not found for this vendor/SKU combination
          const vendorValue = String(vendorName).trim()
          updated[index] = { 
            ...updated[index], 
            vendor: vendorValue
          }
          setPoItems(updated)
        }
      } else if (!vendorName) {
        // Clear vendor selection
        updated[index] = { 
          ...updated[index], 
          vendor: null,
          item_id: null,
          description: '',
          unit_cost: '',
          unit_of_measure: '',
          costMasterData: null
        }
        setPoItems(updated)
      }
      return
    }
    
    // Handle unit_of_measure changes
    if (field === 'unit_of_measure') {
      const updated = [...poItems]
      const currentItem = { ...updated[index] }
      const newUnit = value
      const oldUnit = currentItem.unit_of_measure
      
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
      return
    }
    
    // For other fields, update immediately
    const updated = [...poItems]
    
    // Handle quantity and unit_cost fields - allow empty string
    if (field === 'quantity' || field === 'unit_cost') {
      if (value === '' || value === null || value === undefined) {
        updated[index] = { ...updated[index], [field]: '' }
      } else {
        const numValue = typeof value === 'string' ? parseFloat(value) : value
        updated[index] = { ...updated[index], [field]: isNaN(numValue) ? '' : numValue }
      }
    } else {
      updated[index] = { ...updated[index], [field]: value }
    }
    
    setPoItems(updated)
  }

  // Helper function to load item pricing
  const loadItemPricing = async (index: number, item: Item, vendorValue?: string) => {
    let priceToSet: number | string = ''
    let priceSet = false
    let costMasterData = null
    
    // Priority 1: Use the item's price directly (this is vendor-specific and most accurate)
    if (item.price && item.price > 0) {
      priceToSet = item.price
      priceSet = true
    }
    
    // Priority 2: Try to pull pricing from CostMaster filtered by vendor (if item price not available)
    if (!priceSet && item.sku && vendorValue) {
      try {
        const costMaster = await getCostMasterByProductCode(item.sku, vendorValue)
        if (costMaster) {
          costMasterData = costMaster
          const originalUnit = item.unit_of_measure
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
    
    // Priority 3: Fallback to CostMaster without vendor filter (only if no vendor-specific pricing found)
    if (!priceSet && item.sku) {
      try {
        const costMaster = await getCostMasterByProductCode(item.sku)
        if (costMaster) {
          costMasterData = costMaster
          const originalUnit = item.unit_of_measure
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
        console.error('Failed to load cost master (fallback):', error)
      }
    }
    
    // Update price if we found one - use functional update to preserve all fields including vendor
    if (priceSet) {
      setPoItems(prev => {
        const updated = [...prev]
        updated[index] = { 
          ...updated[index], 
          unit_cost: priceToSet,
          costMasterData: costMasterData,
          // Preserve vendor if it was passed
          vendor: vendorValue !== undefined ? vendorValue : updated[index].vendor
        }
        return updated
      })
    } else {
      // Even if no price, store the cost master data if we have it
      if (costMasterData) {
        setPoItems(prev => {
          const updated = [...prev]
          updated[index] = { 
            ...updated[index], 
            costMasterData: costMasterData,
            // Preserve vendor if it was passed
            vendor: vendorValue !== undefined ? vendorValue : updated[index].vendor
          }
          return updated
        })
      }
    }
  }

  const addItem = () => {
    setPoItems([...poItems, { item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }])
  }

  const removeItem = (index: number) => {
    setPoItems(poItems.filter((_, i) => i !== index))
  }

  const calculateSubtotal = () => {
    return poItems.reduce((sum, item) => {
      const cost = typeof item.unit_cost === 'string' ? parseFloat(item.unit_cost) || 0 : item.unit_cost
      const qty = typeof item.quantity === 'string' ? parseFloat(item.quantity) || 0 : item.quantity
      return sum + (cost * qty)
    }, 0)
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

    // Validate items
    const invalidItems = poItems.filter(item => {
      if (!item.item_id) return true
      const qty = typeof item.quantity === 'string' ? parseFloat(item.quantity) : item.quantity
      return !qty || qty <= 0
    })
    if (poItems.length === 0 || invalidItems.length > 0) {
      alert('Please add at least one item with a selected SKU/Vendor and valid quantity greater than 0')
      return
    }
    
    // Filter out any items without item_id (shouldn't happen after validation, but just in case)
    const validItems = poItems.filter(item => {
      if (!item.item_id) return false
      const qty = typeof item.quantity === 'string' ? parseFloat(item.quantity) : item.quantity
      return qty > 0
    })
    
    if (validItems.length === 0) {
      alert('No valid items to add to purchase order')
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
        items: validItems.map(item => ({
          item_id: item.item_id,
          unit_cost: item.unit_cost || 0,
          quantity: item.quantity,
          notes: '', // Notes field removed from UI
        })),
        discount: formData.discount || 0,
        shipping_cost: formData.shipping_cost || 0,
        status: 'draft',
      }

      console.log('Sending purchase order payload:', JSON.stringify(payload, null, 2))
      await createPurchaseOrder(payload)
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create purchase order:', error)
      console.error('Error response:', error.response?.data)
      console.error('Error status:', error.response?.status)
      const errorMessage = error.response?.data?.detail || 
                          error.response?.data?.message || 
                          error.response?.data?.error ||
                          (error.response?.data && JSON.stringify(error.response.data)) ||
                          error.message || 
                          'Failed to create purchase order'
      alert(`Failed to create purchase order: ${errorMessage}`)
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
                    value={formData.vendor_id || ''}
                    onChange={(e) => {
                      const selectedValue = e.target.value
                      handleVendorChange(selectedValue)
                    }}
                    required
                    disabled={loading || loadingVendors}
                    style={{ width: '100%' }}
                  >
                    <option value="">
                      {loadingVendors ? 'Loading vendors...' : 'Select Vendor'}
                    </option>
                    {!loadingVendors && vendorOptions.length > 0 && vendorOptions.map(vendor => (
                      <option key={vendor.id} value={vendor.value}>
                        {vendor.name}
                      </option>
                    ))}
                    {!loadingVendors && vendorOptions.length === 0 && (
                      <option value="" disabled>No vendors available</option>
                    )}
                  </select>
                  {!loadingVendors && vendors.length === 0 && (
                    <small style={{ color: '#dc3545', display: 'block', marginTop: '5px' }}>
                      No vendors found. Please create vendors first.
                    </small>
                  )}
                  {loadingVendors && (
                    <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                      Loading vendors...
                    </small>
                  )}
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
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {poItems.length > 1 && (
                  <button 
                    type="button" 
                    onClick={() => {
                      const lastIndex = poItems.length - 1
                      if (lastIndex >= 0) {
                        removeItem(lastIndex)
                      }
                    }} 
                    className="btn btn-danger btn-sm"
                    style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
                  >
                    Remove Last Item
                  </button>
                )}
                <button type="button" onClick={addItem} className="btn btn-secondary">+ Add Item</button>
              </div>
            </div>
            
            <table className="po-items-table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Vendor</th>
                  <th>Description</th>
                  <th>Unit of Measure</th>
                  <th>Unit Cost</th>
                  <th>Qty</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {poItems.map((item, index) => {
                  const uniqueSkus = getUniqueSkus()
                  const vendorsForSku = item.sku ? getVendorsForSku(item.sku) : []
                  
                  return (
                  <tr key={index}>
                    <td>
                      <select
                        value={item.sku || ''}
                        onChange={(e) => {
                          handleItemChange(index, 'sku', e.target.value || null)
                        }}
                        required
                        disabled={!formData.vendor_id}
                        className="item-select"
                      >
                        <option value="">
                          {!formData.vendor_id ? 'Select vendor first' : 'Select SKU'}
                        </option>
                        {uniqueSkus.map(sku => (
                          <option key={sku} value={sku}>{sku}</option>
                        ))}
                        {formData.vendor_id && uniqueSkus.length === 0 && (
                          <option value="" disabled>No items available for this vendor</option>
                        )}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={formData.vendor_id ? vendors.find(v => String(v.id) === formData.vendor_id)?.name || '' : ''}
                        readOnly
                        className="read-only-input"
                        style={{ backgroundColor: '#f5f5f5', cursor: 'not-allowed' }}
                      />
                      {/* Hidden select to maintain the vendor value in the item */}
                      <select
                        value={item.vendor || ''}
                        onChange={(e) => {
                          const selectedValue = e.target.value
                          handleItemChange(index, 'vendor', selectedValue || null)
                        }}
                        required
                        disabled={!item.sku || !formData.vendor_id}
                        className="item-select"
                        style={{ display: 'none' }}
                      >
                        <option value="">{item.sku ? 'Select Vendor' : 'Select SKU first'}</option>
                        {vendorsForSku.map(v => {
                          const vendorValue = String(v.vendor || '')
                          return (
                            <option key={`${item.sku}_${v.vendor}`} value={vendorValue}>
                              {v.vendor}
                            </option>
                          )
                        })}
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
                        value={item.unit_cost === '' ? '' : item.unit_cost}
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
                          value={item.quantity === '' ? '' : item.quantity}
                          onChange={(e) => {
                            const val = e.target.value
                            handleItemChange(index, 'quantity', val === '' ? '' : (isNaN(parseFloat(val)) ? '' : parseFloat(val)))
                          }}
                          className="number-input"
                          required
                          style={{ width: '100%' }}
                        />
                      </div>
                    </td>
                    <td>{formatCurrency((typeof item.unit_cost === 'string' ? parseFloat(item.unit_cost) || 0 : item.unit_cost) * (typeof item.quantity === 'string' ? parseFloat(item.quantity) || 0 : item.quantity))}</td>
                  </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={5} className="text-right"><strong>SUBTOTAL</strong></td>
                  <td><strong>{formatCurrency(calculateSubtotal())}</strong></td>
                  <td></td>
                </tr>
                <tr>
                  <td colSpan={5} className="text-right"><strong>DISCOUNT</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.discount || ''}
                      onChange={(e) => setFormData({ ...formData, discount: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
                      className="number-input"
                      style={{ width: '100%', textAlign: 'right' }}
                    />
                  </td>
                  <td></td>
                </tr>
                <tr>
                  <td colSpan={5} className="text-right"><strong>SHIPPING</strong></td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.shipping_cost || ''}
                      onChange={(e) => setFormData({ ...formData, shipping_cost: e.target.value === '' ? 0 : parseFloat(e.target.value) || 0 })}
                      className="number-input"
                      style={{ width: '100%', textAlign: 'right' }}
                    />
                  </td>
                  <td></td>
                </tr>
                <tr>
                  <td colSpan={5} className="text-right"><strong>TOTAL</strong></td>
                  <td><strong>{formatCurrency(calculateTotal())}</strong></td>
                  <td></td>
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


