import { useState, useEffect, useMemo, useCallback } from 'react'
import { createPurchaseOrder } from '../../api/purchaseOrders'
import { getSalesOrder, getSalesOrders } from '../../api/salesOrders'
import { getShipToLocation } from '../../api/customers'
import { getVendors, getVendorContacts } from '../../api/quality'
import { getServiceVendorTypeLabel } from '../../constants/serviceVendorTypes'
import { getItems } from '../../api/inventory'
import { getCostMasterByProductCode } from '../../api/costMaster'
import { formatCurrency } from '../../utils/formatNumber'
import { useGodMode } from '../../context/GodModeContext'
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

interface ItemPackSizeRow {
  id?: number
  pack_size: number
  pack_size_unit: string
  description?: string | null
  is_default?: boolean
  is_active?: boolean
  pack_size_display?: string
}

interface Item {
  id: number
  name: string
  sku: string
  unit_of_measure: string
  price?: number
  pack_size?: number
  default_pack_size?: ItemPackSizeRow | null
  pack_sizes?: ItemPackSizeRow[]
  vendor_item_name?: string
  vendor_item_number?: string | null
  display_name_for_vendor?: string
}

/** One-line hint for PO qty column: default pack size or list from item master. */
function formatPackSizeHint(catalogItem: Item | undefined): string | null {
  if (!catalogItem) return null
  const fmt = (p: ItemPackSizeRow) => {
    const base = (p.pack_size_display || '').trim() || `${p.pack_size} ${p.pack_size_unit}`
    const d = (p.description || '').trim()
    return d ? `${base} — ${d}` : base
  }
  if (catalogItem.default_pack_size) {
    return `Pack size: ${fmt(catalogItem.default_pack_size)} (default)`
  }
  const list = (catalogItem.pack_sizes || []).filter((p) => p.is_active !== false)
  if (list.length > 0) {
    const parts = list.slice(0, 5).map(fmt)
    const more = list.length > 5 ? ` (+${list.length - 5} more)` : ''
    return `Pack sizes: ${parts.join(' · ')}${more}`
  }
  if (catalogItem.pack_size != null && catalogItem.pack_size > 0) {
    return `Pack size (legacy): ${catalogItem.pack_size}`
  }
  return null
}

function vendorDescriptionForPoLine(item: Item): string {
  const name = item.display_name_for_vendor || item.vendor_item_name || item.name
  const num = (item.vendor_item_number || '').trim()
  return num ? `${name} (${num})` : name
}

/** Round money to 2 decimal places (matches unit cost input step="0.01"). */
function roundMoney2(n: number): number {
  return Number.parseFloat(n.toFixed(2))
}

/** Default ship-to when not drop-shipping (Wildwood warehouse). */
const DEFAULT_WW_SHIP_TO = {
  ship_to_name: 'Wildwood Ingredients, LLC',
  ship_to_address: '6431 Michels Dr.',
  ship_to_city: 'Washington',
  ship_to_state: 'MO',
  ship_to_zip: '63090',
  ship_to_country: 'USA',
} as const

/**
 * Match backend apply_sales_order_ship_to_to_purchase_order — ship-to for vendor drop ship PO.
 */
function shipToFieldsFromSalesOrder(so: {
  customer_name?: string
  customer?: { name?: string } | null
  ship_to_location?: {
    location_name?: string
    address?: string
    city?: string
    state?: string | null
    zip_code?: string
    country?: string
  } | null
  customer_address?: string | null
  customer_city?: string | null
  customer_state?: string | null
  customer_zip?: string | null
  customer_country?: string | null
}): {
  ship_to_name: string
  ship_to_address: string
  ship_to_city: string
  ship_to_state: string
  ship_to_zip: string
  ship_to_country: string
} {
  const loc = so.ship_to_location
  const custName = so.customer?.name || so.customer_name || ''
  if (loc) {
    const name = custName
      ? `${custName} — ${loc.location_name || 'Ship-to'}`
      : (loc.location_name || 'Ship-to')
    return {
      ship_to_name: name.slice(0, 255),
      ship_to_address: (loc.address || '').replace(/\n/g, ' ').trim().slice(0, 255),
      ship_to_city: (loc.city || '').slice(0, 255),
      ship_to_state: (loc.state || '').slice(0, 100),
      ship_to_zip: String(loc.zip_code || '').slice(0, 20),
      ship_to_country: (loc.country || 'USA').slice(0, 100),
    }
  }
  const fallbackName = (so.customer_name || so.customer?.name || 'Ship-to').slice(0, 255)
  return {
    ship_to_name: fallbackName,
    ship_to_address: (so.customer_address || '').replace(/\n/g, ' ').trim().slice(0, 255),
    ship_to_city: (so.customer_city || '').slice(0, 255),
    ship_to_state: (so.customer_state || '').slice(0, 100),
    ship_to_zip: String(so.customer_zip || '').slice(0, 20),
    ship_to_country: (so.customer_country || 'USA').slice(0, 100),
  }
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
  const { godModeOn, canUseGodMode, maxDateForEntry, minDateForEntry } = useGodMode()
  const todayYmd = useCallback(() => {
    const d = new Date()
    return (
      d.getFullYear() +
      '-' +
      String(d.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(d.getDate()).padStart(2, '0')
    )
  }, [])

  const [vendors, setVendors] = useState<Vendor[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingVendors, setLoadingVendors] = useState(true)
  
  const [formData, setFormData] = useState({
    order_number: '',
    vendor_id: '',
    order_date: todayYmd(),
    required_date: '',
    expected_delivery_date: '',
    shipping_terms: '',
    shipping_method: '',
    ...DEFAULT_WW_SHIP_TO,
    vendor_address: '',
    vendor_city: '',
    vendor_state: '',
    vendor_zip: '',
    vendor_country: '',
    coa_sds_email: '',
    discount: 0,
    shipping_cost: 0,
    notes: '',
    drop_ship: false,
    fulfillment_sales_order_id: '' as string,
  })

  const [poItems, setPoItems] = useState<POItem[]>([
    { item_id: null, sku: null, vendor: null, description: '', unit_cost: '', unit_of_measure: '', quantity: '', notes: '', original_unit: '', costMasterData: null }
  ])
  const [notifyPartyServiceVendorId, setNotifyPartyServiceVendorId] = useState<string>('')
  const [notifyPartyContacts, setNotifyPartyContacts] = useState<
    { id: number; name: string; email?: string; emails?: string[]; phone?: string; location_label?: string; notes?: string }[]
  >([])
  const [notifyPartyContactIds, setNotifyPartyContactIds] = useState<number[]>([])
  const [linkableSalesOrders, setLinkableSalesOrders] = useState<
    { id: number; so_number: string; customer_name: string; status: string; drop_ship?: boolean }[]
  >([])
  const [fulfillmentSoLoading, setFulfillmentSoLoading] = useState(false)

  const handleFulfillmentSoChange = async (raw: string) => {
    if (!raw) {
      setFormData((prev) => ({
        ...prev,
        fulfillment_sales_order_id: '',
        ...DEFAULT_WW_SHIP_TO,
      }))
      return
    }
    setFulfillmentSoLoading(true)
    try {
      const soRaw = await getSalesOrder(parseInt(raw, 10))
      let loc: unknown = soRaw.ship_to_location
      if (typeof loc === 'number') {
        try {
          loc = await getShipToLocation(loc)
        } catch {
          loc = null
        }
      }
      const so = {
        ...soRaw,
        ship_to_location:
          loc && typeof loc === 'object'
            ? (loc as {
                location_name?: string
                address?: string
                city?: string
                state?: string | null
                zip_code?: string
                country?: string
              })
            : null,
      }
      const st = shipToFieldsFromSalesOrder(so)
      setFormData((prev) => ({
        ...prev,
        fulfillment_sales_order_id: raw,
        ...st,
      }))
    } catch (err) {
      console.error(err)
      alert('Could not load that sales order to fill ship-to. Try again or enter ship-to manually.')
      setFormData((prev) => ({ ...prev, fulfillment_sales_order_id: '' }))
    } finally {
      setFulfillmentSoLoading(false)
    }
  }

  useEffect(() => {
    loadVendors()
    loadItems()
    getSalesOrders({ drop_ship: 'true' })
      .then((data) => {
        const list = Array.isArray(data) ? data : ((data as { results?: unknown[] }).results ?? [])
        setLinkableSalesOrders(
          (
            list as {
              id: number
              so_number: string
              customer_name: string
              status: string
              drop_ship?: boolean
            }[]
          ).filter((so) => so.status !== 'completed' && so.status !== 'cancelled')
        )
      })
      .catch(() => setLinkableSalesOrders([]))
  }, [])

  useEffect(() => {
    if (!notifyPartyServiceVendorId) {
      setNotifyPartyContacts([])
      setNotifyPartyContactIds([])
      return
    }
    getVendorContacts(parseInt(notifyPartyServiceVendorId, 10))
      .then((list: any[]) => {
        setNotifyPartyContacts(Array.isArray(list) ? list : [])
        setNotifyPartyContactIds([])
      })
      .catch(() => {
        setNotifyPartyContacts([])
        setNotifyPartyContactIds([])
      })
  }, [notifyPartyServiceVendorId])

  const toggleNotifyPartyContact = (contactId: number) => {
    setNotifyPartyContactIds(prev =>
      prev.includes(contactId) ? prev.filter(id => id !== contactId) : [...prev, contactId]
    )
  }

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
          const displayName = vendorDescriptionForPoLine(matchingItem)
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
          const displayName = vendorDescriptionForPoLine(matchingItem)
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
        const parsedLineCost =
          typeof currentItem.unit_cost === 'string'
            ? parseFloat(currentItem.unit_cost)
            : Number(currentItem.unit_cost)

        let newPrice: number | string = currentItem.unit_cost

        // Recalculate unit cost based on cost master data
        if (currentItem.costMasterData) {
          const costMaster = currentItem.costMasterData

          if (newUnit === 'lbs' && costMaster.price_per_lb) {
            newPrice = costMaster.price_per_lb
          } else if (newUnit === 'kg' && costMaster.price_per_kg) {
            newPrice = costMaster.price_per_kg
          } else if (newUnit === 'lbs' && costMaster.price_per_kg) {
            newPrice = costMaster.price_per_kg / 2.20462
          } else if (newUnit === 'kg' && costMaster.price_per_lb) {
            newPrice = costMaster.price_per_lb * 2.20462
          } else {
            if (oldUnit === 'lbs' && newUnit === 'kg') {
              newPrice = Number.isFinite(parsedLineCost) ? parsedLineCost * 2.20462 : NaN
            } else if (oldUnit === 'kg' && newUnit === 'lbs') {
              newPrice = Number.isFinite(parsedLineCost) ? parsedLineCost / 2.20462 : NaN
            }
          }
        } else {
          if (oldUnit === 'lbs' && newUnit === 'kg') {
            newPrice = Number.isFinite(parsedLineCost) ? parsedLineCost * 2.20462 : NaN
          } else if (oldUnit === 'kg' && newUnit === 'lbs') {
            newPrice = Number.isFinite(parsedLineCost) ? parsedLineCost / 2.20462 : NaN
          }
        }

        const rawNum =
          typeof newPrice === 'number'
            ? newPrice
            : typeof newPrice === 'string' && newPrice !== ''
              ? parseFloat(newPrice)
              : NaN
        const unitCostRounded = Number.isFinite(rawNum) ? roundMoney2(rawNum) : newPrice

        updated[index] = {
          ...currentItem,
          unit_of_measure: newUnit,
          unit_cost: unitCostRounded
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
      priceToSet = roundMoney2(item.price)
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
      const unitCostFinal =
        typeof priceToSet === 'number' && Number.isFinite(priceToSet) ? roundMoney2(priceToSet) : priceToSet
      setPoItems(prev => {
        const updated = [...prev]
        updated[index] = {
          ...updated[index],
          unit_cost: unitCostFinal,
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
      
      const payload: Record<string, unknown> = {
        ...formData,
        vendor_id: parseInt(formData.vendor_id),
        order_number: formData.order_number || null,
        po_number: formData.order_number?.trim() || null,
        required_date: formData.required_date || formData.expected_delivery_date || null,
        expected_delivery_date: formData.expected_delivery_date || formData.required_date || null,
        notify_party_contact_ids: notifyPartyContactIds.length ? notifyPartyContactIds : undefined,
        drop_ship: formData.drop_ship,
        fulfillment_sales_order:
          formData.drop_ship && formData.fulfillment_sales_order_id
            ? parseInt(String(formData.fulfillment_sales_order_id), 10)
            : null,
        items: validItems.map((item) => ({
          item_id: item.item_id,
          unit_cost: roundMoney2(
            typeof item.unit_cost === 'string'
              ? parseFloat(item.unit_cost) || 0
              : (item.unit_cost as number) || 0
          ),
          quantity: item.quantity,
          order_uom: (item.unit_of_measure || '').trim() || null,
          notes: (item.notes || '').trim() || '',
        })),
        discount: formData.discount || 0,
        shipping_cost: formData.shipping_cost || 0,
        status: 'draft',
      }
      delete payload.fulfillment_sales_order_id

      if (godModeOn && canUseGodMode && formData.order_date) {
        payload.order_date = `${formData.order_date}T12:00:00`
      } else {
        delete payload.order_date
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
                  <label>PO date</label>
                  {godModeOn && canUseGodMode ? (
                    <input
                      type="date"
                      value={formData.order_date}
                      onChange={(e) => setFormData({ ...formData, order_date: e.target.value })}
                      max={maxDateForEntry}
                      min={minDateForEntry}
                    />
                  ) : (
                    <input type="date" value={todayYmd()} readOnly />
                  )}
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
                  <label className="checkbox-label" style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={formData.drop_ship}
                      onChange={(e) => {
                        const v = e.target.checked
                        setFormData((prev) => ({
                          ...prev,
                          drop_ship: v,
                          fulfillment_sales_order_id: v ? prev.fulfillment_sales_order_id : '',
                          ...(v ? {} : DEFAULT_WW_SHIP_TO),
                        }))
                      }}
                    />
                    <span>
                      <strong>Drop ship</strong> — vendor ships direct to customer (not to Wildwood). Ship-to below can be filled from a linked sales order.
                    </span>
                  </label>
                  <p className="form-hint" style={{ marginTop: 6 }}>
                    Do not check in inventory against this PO. Link the sales order you created from the customer PO so the vendor ship-to matches.
                  </p>
                </div>
                {formData.drop_ship && (
                  <div className="form-group">
                    <label>Fulfillment sales order</label>
                    <select
                      value={formData.fulfillment_sales_order_id}
                      onChange={(e) => void handleFulfillmentSoChange(e.target.value)}
                      disabled={fulfillmentSoLoading}
                      style={{ width: '100%' }}
                    >
                      <option value="">— Select sales order —</option>
                      {linkableSalesOrders.map((so) => (
                        <option key={so.id} value={so.id}>
                          {so.so_number} — {so.customer_name || 'Customer'} ({so.status})
                        </option>
                      ))}
                    </select>
                    {fulfillmentSoLoading && (
                      <p className="form-hint" style={{ marginTop: 6 }}>
                        Loading ship-to from sales order…
                      </p>
                    )}
                    {linkableSalesOrders.length === 0 && (
                      <p className="form-hint" style={{ marginTop: 6 }}>
                        Only sales orders marked <strong>Drop ship</strong> (and not completed/cancelled) can be linked. Create or edit the SO on Sales and enable Drop ship first.
                      </p>
                    )}
                  </div>
                )}
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
            <h3>Notify party</h3>
            <p className="form-hint" style={{ marginBottom: 8 }}>Optional: select one or more contacts that handle importation (e.g. customs broker by port). These appear on the PO PDF.</p>
            <div className="form-row">
              <div className="form-group">
                <label>Service vendor (e.g. customs broker)</label>
                <select
                  value={notifyPartyServiceVendorId}
                  onChange={(e) => setNotifyPartyServiceVendorId(e.target.value)}
                  style={{ width: '100%' }}
                >
                  <option value="">— None —</option>
                  {vendors.filter(v => v.is_service_vendor).map(v => (
                    <option key={v.id} value={v.id}>{v.name}{v.service_vendor_type ? ` (${getServiceVendorTypeLabel(v.service_vendor_type)})` : ''}</option>
                  ))}
                </select>
              </div>
              <div className="form-group notify-party-contacts-multi">
                <label>Contact(s) (notify party)</label>
                {!notifyPartyServiceVendorId ? (
                  <p className="form-hint">Select a service vendor first.</p>
                ) : notifyPartyContacts.length === 0 ? (
                  <p className="form-hint">No contacts for this vendor. Add contacts in Quality → Vendors → vendor → Contacts.</p>
                ) : (
                  <div className="notify-party-checkboxes">
                    {notifyPartyContacts.map(c => (
                      <label key={c.id} className="notify-party-checkbox">
                        <input
                          type="checkbox"
                          checked={notifyPartyContactIds.includes(c.id)}
                          onChange={() => toggleNotifyPartyContact(c.id)}
                        />
                        <span>
                          {c.name}
                          {c.location_label ? ` — ${c.location_label}` : ''}
                          {(c.emails || []).length > 0 && (
                            <div className="notify-party-emails">{c.emails!.join(', ')}</div>
                          )}
                          {c.notes && <div className="notify-party-notes">Notes: {c.notes}</div>}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
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
                  <th>Unit cost</th>
                  <th>Qty</th>
                  <th>Line notes</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {poItems.map((item, index) => {
                  const uniqueSkus = getUniqueSkus()
                  const vendorsForSku = item.sku ? getVendorsForSku(item.sku) : []
                  const catalogItem = item.item_id ? items.find((i) => i.id === item.item_id) : undefined
                  const packSizeHint = formatPackSizeHint(catalogItem)

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
                        onChange={(e) => {
                          const v = e.target.value
                          handleItemChange(index, 'unit_cost', v === '' ? '' : parseFloat(v))
                        }}
                        onBlur={(e) => {
                          const v = e.target.value
                          if (v === '') return
                          const n = parseFloat(v)
                          if (!Number.isFinite(n)) return
                          const r = roundMoney2(n)
                          if (r !== n) handleItemChange(index, 'unit_cost', r)
                        }}
                        className="number-input"
                        title="Override if the price differs from item / cost master"
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
                        {packSizeHint ? (
                          <small className="po-qty-pack-hint" title="From item master (pack sizes)">
                            {packSizeHint}
                          </small>
                        ) : null}
                      </div>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={item.notes}
                        onChange={(e) => handleItemChange(index, 'notes', e.target.value)}
                        placeholder="Optional"
                        className="po-line-notes-input"
                      />
                    </td>
                    <td>{formatCurrency((typeof item.unit_cost === 'string' ? parseFloat(item.unit_cost) || 0 : item.unit_cost) * (typeof item.quantity === 'string' ? parseFloat(item.quantity) || 0 : item.quantity))}</td>
                  </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={7} className="text-right"><strong>SUBTOTAL</strong></td>
                  <td><strong>{formatCurrency(calculateSubtotal())}</strong></td>
                </tr>
                <tr>
                  <td colSpan={7} className="text-right"><strong>DISCOUNT</strong></td>
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
                </tr>
                <tr>
                  <td colSpan={7} className="text-right"><strong>SHIPPING</strong></td>
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
                </tr>
                <tr>
                  <td colSpan={7} className="text-right"><strong>TOTAL</strong></td>
                  <td><strong>{formatCurrency(calculateTotal())}</strong></td>
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
              <label>PO comments / notes</label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={4}
                placeholder="Internal comments, special terms, or instructions for this PO"
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


