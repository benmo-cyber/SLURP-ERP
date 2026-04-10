import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { createSalesOrder, updateSalesOrder, getSalesOrder, parseCustomerPo, uploadCustomerPo, type ParsedCustomerPO } from '../../api/salesOrders'
import { getItems } from '../../api/inventory'
import { getCustomers, getShipToLocations, getCustomerPricing, getCustomerContacts } from '../../api/customers'
import { formatNumber, formatCurrency } from '../../utils/formatNumber'
import { useGodMode } from '../../context/GodModeContext'
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
  salesOrder?: any // Optional: if provided, component works in edit mode
}

function CreateSalesOrder({ onClose, onSuccess, salesOrder }: CreateSalesOrderProps) {
  const { godModeOn, canUseGodMode, maxDateForEntry, minDateForEntry } = useGodMode()
  const todayYmd = useMemo(() => {
    const d = new Date()
    return (
      d.getFullYear() +
      '-' +
      String(d.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(d.getDate()).padStart(2, '0')
    )
  }, [])
  const [items, setItems] = useState<Item[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [shipToLocations, setShipToLocations] = useState<ShipToLocation[]>([])
  const [customerPricing, setCustomerPricing] = useState<CustomerPricing[]>([])
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null)
  const [selectedShipToId, setSelectedShipToId] = useState<number | null>(null)
  const [contacts, setContacts] = useState<{ id: number; first_name: string; last_name: string; contact_type?: string }[]>([])
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [poUploadDragOver, setPoUploadDragOver] = useState(false)
  const [poParseLoading, setPoParseLoading] = useState(false)
  const [poParseWarning, setPoParseWarning] = useState<string | null>(null)
  const [poParseSuccess, setPoParseSuccess] = useState<string | null>(null)
  const [poExtractedPreview, setPoExtractedPreview] = useState<string | null>(null)
  const [pendingPoFile, setPendingPoFile] = useState<File | null>(null)
  const [customerPoPdfUrl, setCustomerPoPdfUrl] = useState<string | null>(null)
  const poFileInputRef = useRef<HTMLInputElement>(null)
  
  const [formData, setFormData] = useState({
    so_number: '', // Leave blank for auto-generation; set for legacy / God mode
    order_date: todayYmd,
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
    drop_ship: false,
  })

  const [soItems, setSoItems] = useState<SOItem[]>([
    { item_id: null, vendor_part_number: '', description: '', quantity_ordered: '', unit: '', unit_price: '', notes: '' }
  ])
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  /** While typing "12." on mass UoM price (display unit), hold raw string so toggle math + manual edit both work */
  const [unitPriceDrafts, setUnitPriceDrafts] = useState<Record<number, string>>({})

  useEffect(() => {
    loadItems()
    loadCustomers()
    if (salesOrder) {
      loadSalesOrderData()
    }
  }, [salesOrder])

  useEffect(() => {
    if (selectedCustomerId) {
      loadShipToLocations(selectedCustomerId)
      loadCustomerPricing(selectedCustomerId)
      loadCustomerContacts(selectedCustomerId)
    } else {
      setShipToLocations([])
      setSelectedShipToId(null)
      setCustomerPricing([])
      setContacts([])
      setSelectedContactId(null)
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
    setUnitPriceDrafts({})
  }, [unitDisplay])

  useEffect(() => {
    calculateTotals()
  }, [soItems, formData.freight, formData.misc, formData.prepaid, formData.discount])

  // When customer pricing loads, try to match parsed line item descriptions to items and auto-select
  useEffect(() => {
    if (!selectedCustomerId || customerPricing.length === 0) return
    setSoItems(prev => prev.map(row => {
      if (row.item_id != null) return row
      const desc = (row.description || '').toLowerCase().trim()
      if (!desc) return row
      const match = customerPricing.find(p => {
        const name = (p.item?.name || '').toLowerCase()
        const sku = (p.item?.sku || '').toLowerCase()
        return name && (desc.includes(name) || name.includes(desc) || (sku && (desc.includes(sku) || sku.includes(desc))))
      })
      if (match) {
        const keepPrice =
          row.unit_price !== '' && row.unit_price !== null && row.unit_price !== undefined
        return {
          ...row,
          item_id: match.item_id,
          unit: row.unit || match.unit_of_measure,
          unit_price: keepPrice ? row.unit_price : match.unit_price,
        }
      }
      return row
    }))
  }, [selectedCustomerId, customerPricing])

  const applyParsedPo = useCallback((parsed: ParsedCustomerPO) => {
    setFormData(prev => ({
      ...prev,
      customer_id: parsed.customer_po_number || prev.customer_id,
      customer_reference_number: parsed.customer_po_number ? (prev.customer_reference_number || parsed.customer_po_number) : prev.customer_reference_number,
      customer_name: parsed.customer_name || prev.customer_name,
      customer_address: parsed.customer_address || prev.customer_address,
      customer_city: parsed.customer_city || prev.customer_city,
      customer_state: parsed.customer_state || prev.customer_state,
      customer_zip: parsed.customer_zip || prev.customer_zip,
      customer_country: parsed.customer_country || prev.customer_country,
      customer_phone: parsed.customer_phone || prev.customer_phone,
      requested_ship_date: parsed.requested_ship_date || prev.requested_ship_date,
    }))
    if (parsed.customer_name && customers.length > 0) {
      const want = parsed.customer_name.toLowerCase().replace(/\s+/g, ' ').trim()
      const match = customers.find(c => {
        const n = c.name.toLowerCase()
        return n === want || n.includes(want) || want.includes(n) ||
          n.replace(/\b(inc|llc|corp|co|ltd|company)\b\.?/gi, '').trim().includes(want.split(/\s+/)[0] || '')
      })
      if (match) setSelectedCustomerId(match.id)
    }
    if (parsed.items && parsed.items.length > 0) {
      const newItems: SOItem[] = parsed.items.map(it => ({
        item_id: null,
        vendor_part_number: it.vendor_part_number || '',
        description: it.description || '',
        quantity_ordered: it.quantity_ordered,
        unit: it.unit || 'lbs',
        unit_price: it.unit_price,
        notes: it.notes || '',
      }))
      setSoItems(newItems)
    }
  }, [customers])

  const handlePoFile = useCallback(async (file: File | null) => {
    if (!file) return
    const allowed = ['application/pdf', 'text/plain', 'text/csv']
    const ok = allowed.includes(file.type) || file.name.toLowerCase().endsWith('.pdf') || file.name.toLowerCase().endsWith('.txt')
    if (!ok) {
      alert('Please upload a PDF or text file.')
      return
    }
    setPoParseLoading(true)
    setPoParseWarning(null)
    setPoParseSuccess(null)
    setPoExtractedPreview(null)
    setPendingPoFile(file)
    try {
      const parsed = await parseCustomerPo(file)
      setPoParseWarning(parsed.warning || null)
      setPoExtractedPreview(parsed.extracted_preview || null)
      applyParsedPo(parsed)
      const filled: string[] = []
      if (parsed.customer_po_number) filled.push('PO number')
      if (parsed.customer_name) filled.push('customer name')
      if (parsed.customer_address || parsed.customer_city) filled.push('address')
      if (parsed.requested_ship_date) filled.push('ship date')
      if (parsed.items?.length) filled.push(`${parsed.items.length} line item(s)`)
      setPoParseSuccess(filled.length ? `Filled: ${filled.join(', ')}. Review and select Customer / Item where needed.` : (parsed.extracted_preview ? 'Text was extracted but no fields matched. Check "Extracted text" below and enter manually.' : null))
    } catch (err: any) {
      setPendingPoFile(null)
      const msg = err.response?.data?.error || err.response?.data?.detail || err.message || 'Failed to parse document'
      alert(msg)
    } finally {
      setPoParseLoading(false)
    }
  }, [applyParsedPo])

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

  const loadSalesOrderData = async () => {
    if (!salesOrder) return
    
    try {
      setLoading(true)
      const orderData = await getSalesOrder(salesOrder.id)
      
      // Set customer
      if (orderData.customer) {
        setSelectedCustomerId(orderData.customer.id)
        try {
          const contactList = await getCustomerContacts(orderData.customer.id)
          const list = Array.isArray(contactList) ? contactList : (contactList?.results ?? [])
          setContacts(list)
        } catch {
          setContacts([])
        }
      }
      
      // Set ship-to location
      if (orderData.ship_to_location) {
        setSelectedShipToId(orderData.ship_to_location.id)
      }
      // Set contact
      if (orderData.contact) {
        setSelectedContactId(orderData.contact.id)
      } else {
        setSelectedContactId(null)
      }
      
      // Set form data
      setFormData({
        so_number: orderData.so_number || '',
        order_date: orderData.order_date ? orderData.order_date.slice(0, 10) : todayYmd,
        customer_reference_number: orderData.customer_reference_number || '',
        customer_name: orderData.customer_name || '',
        // Form field labeled "Customer PO Number" — not API customer_id (FK)
        customer_id:
          orderData.customer_reference_number ||
          (orderData as { customer_legacy_id?: string }).customer_legacy_id ||
          '',
        customer_address: orderData.customer_address || '',
        customer_city: orderData.customer_city || '',
        customer_state: orderData.customer_state || '',
        customer_zip: orderData.customer_zip || '',
        customer_country: orderData.customer_country || '',
        customer_phone: orderData.customer_phone || '',
        requested_ship_date: orderData.expected_ship_date ? orderData.expected_ship_date.split('T')[0] : '',
        subtotal: orderData.subtotal || 0,
        freight: orderData.freight || 0,
        misc: orderData.misc || 0,
        prepaid: orderData.prepaid || 0,
        discount: orderData.discount || 0,
        grand_total: orderData.grand_total || 0,
        notes: orderData.notes || '',
        drop_ship: !!(orderData as { drop_ship?: boolean }).drop_ship,
      })
      
      // Set items
      if (orderData.items && orderData.items.length > 0) {
        const formattedItems = orderData.items.map((item: any) => ({
          item_id: item.item?.id || null,
          vendor_part_number: item.item?.sku || '',
          description: item.item?.name || '',
          quantity_ordered: item.quantity_ordered || '',
          unit: item.item?.unit_of_measure || '',
          unit_price: item.unit_price || '',
          notes: item.notes || '',
        }))
        setSoItems(formattedItems)
      }
      setCustomerPoPdfUrl(orderData.customer_po_pdf_url || null)
    } catch (error) {
      console.error('Failed to load sales order data:', error)
      alert('Failed to load sales order data')
    } finally {
      setLoading(false)
    }
  }

  const loadCustomerContacts = async (customerId: number) => {
    try {
      const data = await getCustomerContacts(customerId)
      const list = Array.isArray(data) ? data : (data?.results ?? [])
      setContacts(list)
      setSelectedContactId(null)
    } catch (error) {
      console.error('Failed to load contacts:', error)
      setContacts([])
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
      const data = await getCustomerPricing(customerId, undefined, true)
      const pricingList = Array.isArray(data) ? data : []

      // Dates as ISO strings from the API may include a time part; string-compare to YYYY-MM-DD only.
      const toYmd = (v: unknown): string => {
        if (v == null || v === '') return ''
        const s = String(v)
        const m = s.match(/^(\d{4}-\d{2}-\d{2})/)
        return m ? m[1] : s.slice(0, 10)
      }

      // Server already applies current_only (effective / expiry / active). Dedupe by item_id: keep latest effective row.
      const pricingMap = new Map<number, CustomerPricing>()
      ;(pricingList as any[]).forEach((pricing: any) => {
        const itemId = pricing.item_id || pricing.item?.id
        if (!itemId) {
          console.warn('Pricing record missing item_id:', pricing)
          return
        }
        const existing = pricingMap.get(itemId)
        const ed = toYmd(pricing.effective_date)
        const exEd = existing ? toYmd(existing.effective_date) : ''
        if (!existing || ed > exEd) {
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

      const finalPricing = Array.from(pricingMap.values()).sort((a, b) => {
        const sa = (a.item.sku || a.item.name || '').toLowerCase()
        const sb = (b.item.sku || b.item.name || '').toLowerCase()
        return sa.localeCompare(sb)
      })
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
    setSelectedShipToId(null)
    setSelectedContactId(null)
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
    if (field === 'item_id') {
      setUnitPriceDrafts((prev) => {
        const next = { ...prev }
        delete next[index]
        return next
      })
    }

    // Functional update so rapid keystrokes / multiple fields never clobber each other (stale soItems closure).
    setSoItems((prev) => {
      const updated = [...prev]
      const row = { ...updated[index] }
      updated[index] = row
      ;(row as any)[field] = value

      if (field === 'item_id' && value) {
        const itemId = typeof value === 'number' ? value : parseInt(String(value), 10)
        const pricing = customerPricing.find((p) => p.item_id === itemId)
        if (pricing && pricing.item) {
          row.description = pricing.item.name || ''
          row.unit = pricing.unit_of_measure
          row.unit_price = pricing.unit_price
        } else {
          const item = items.find((i) => i.id === itemId)
          if (item) {
            row.description = item.name
            row.unit = item.unit_of_measure
          }
        }
      }

      if (field === 'quantity_ordered' || field === 'unit_price') {
        const v = (row as any)[field]
        if (v === '' || v === null || v === undefined) {
          ;(row as any)[field] = ''
        } else if (typeof v === 'string') {
          const t = v.trim()
          if (t === '' || t === '.') {
            ;(row as any)[field] = ''
          } else if (/^\d+\.$/.test(t)) {
            ;(row as any)[field] = t
          } else {
            const numValue = parseFloat(t)
            ;(row as any)[field] = isNaN(numValue) ? '' : numValue
          }
        } else {
          const numValue = v as number
          ;(row as any)[field] = isNaN(numValue) ? '' : numValue
        }
      }

      return updated
    })
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

  /** Convert price-per-unit from one UoM to another (e.g. $/lb → $/kg). Used so quantity and unit_price are always in the same unit. */
  const convertPricePerUnit = (price: number, fromUnit: string, toUnit: string): number => {
    const f = (fromUnit || '').toLowerCase()
    const t = (toUnit || '').toLowerCase()
    if (f === 'lbs' && t === 'kg') return price * 2.20462  // $/lb → $/kg
    if (f === 'kg' && t === 'lbs') return price / 2.20462   // $/kg → $/lb
    return price
  }

  /** Quantity in row's stored unit → value to show in input when unitDisplay is active */
  const quantityForDisplay = (row: SOItem): string | number => {
    const qty = typeof row.quantity_ordered === 'string' ? parseFloat(row.quantity_ordered) : row.quantity_ordered
    if (qty === '' || (typeof qty === 'number' && isNaN(qty))) return ''
    const u = (row.unit || '').toLowerCase()
    if ((u === 'lbs' || u === 'kg') && u !== unitDisplay) {
      const converted = convertUnit(Number(qty), row.unit, unitDisplay)
      return converted === Math.round(converted) ? converted : Math.round(converted * 100) / 100
    }
    return qty
  }

  /** User edited value in display unit → stored value in row.unit */
  const handleQuantityChange = (index: number, inputValue: string) => {
    const row = soItems[index]
    if (inputValue === '') {
      handleItemChange(index, 'quantity_ordered', '')
      return
    }
    const t = inputValue.trim()
    if (/^\d+\.$/.test(t)) {
      handleItemChange(index, 'quantity_ordered', t)
      return
    }
    const parsed = parseFloat(inputValue)
    if (isNaN(parsed)) return
    const u = (row.unit || '').toLowerCase()
    const stored = (u === 'lbs' || u === 'kg') && u !== unitDisplay
      ? convertUnit(parsed, unitDisplay, row.unit)
      : parsed
    const storedRounded = stored === Math.round(stored) ? stored : Math.round(stored * 100) / 100
    handleItemChange(index, 'quantity_ordered', storedRounded)
  }

  /** Stored $/line-unit → value shown when lbs/kg line uses quantity toggle */
  const unitPriceForDisplay = (row: SOItem): string | number => {
    if (row.unit_price === '' || row.unit_price === null || row.unit_price === undefined) return ''
    const price = typeof row.unit_price === 'string' ? parseFloat(row.unit_price) : row.unit_price
    if (typeof price === 'number' && isNaN(price)) return ''
    const u = (row.unit || '').toLowerCase()
    if (u === 'lbs' && unitDisplay === 'kg') return Math.round(Number(price) * 2.20462 * 100) / 100
    if (u === 'kg' && unitDisplay === 'lbs') return Math.round((Number(price) / 2.20462) * 100) / 100
    return price
  }

  const getUnitPriceInputValue = (index: number, row: SOItem): string => {
    if (unitPriceDrafts[index] !== undefined) return unitPriceDrafts[index]
    const u = (row.unit || '').toLowerCase()
    if (u === 'lbs' || u === 'kg') {
      const v = unitPriceForDisplay(row)
      if (v === '' || v === null || (typeof v === 'number' && isNaN(v))) return ''
      return String(v)
    }
    if (row.unit_price === '' || row.unit_price === null || row.unit_price === undefined) return ''
    return String(row.unit_price)
  }

  /** Mass UoM: user edits in toggle unit ($/lb or $/kg); we store in line unit */
  const handleUnitPriceInputChange = (index: number, raw: string) => {
    const row = soItems[index]
    const u = (row.unit || '').toLowerCase()
    const t = raw.trim()

    if (t === '') {
      setUnitPriceDrafts((prev) => {
        const next = { ...prev }
        delete next[index]
        return next
      })
      handleItemChange(index, 'unit_price', '')
      return
    }
    if (/^\d+\.$/.test(t)) {
      setUnitPriceDrafts((prev) => ({ ...prev, [index]: t }))
      return
    }

    setUnitPriceDrafts((prev) => {
      const next = { ...prev }
      delete next[index]
      return next
    })

    const parsed = parseFloat(t)
    if (isNaN(parsed)) return

    if (u === 'lbs' && unitDisplay === 'kg') {
      const stored = parsed / 2.20462
      handleItemChange(index, 'unit_price', Math.round(stored * 100) / 100)
    } else if (u === 'kg' && unitDisplay === 'lbs') {
      const stored = parsed * 2.20462
      handleItemChange(index, 'unit_price', Math.round(stored * 100) / 100)
    } else {
      const rounded = parsed === Math.round(parsed) ? parsed : Math.round(parsed * 100) / 100
      handleItemChange(index, 'unit_price', rounded)
    }
  }

  const commitUnitPriceDraftIfNeeded = (index: number) => {
    const d = unitPriceDrafts[index]
    if (d != null && /^\d+\.$/.test(d)) {
      setUnitPriceDrafts((prev) => {
        const next = { ...prev }
        delete next[index]
        return next
      })
      handleUnitPriceInputChange(index, d.slice(0, -1))
    }
  }

  const calculateTotals = () => {
    const subtotal = soItems.reduce((sum, item) => {
      const rawP = item.unit_price
      const price =
        rawP === '' || rawP === null || rawP === undefined
          ? 0
          : typeof rawP === 'string'
            ? parseFloat(rawP) || 0
            : rawP
      const qty = typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) || 0 : item.quantity_ordered
      return sum + (Number(price) * Number(qty))
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
      
      // PO / reference: never send `customer_id` in the JSON — DRF uses that key for the Customer FK (integer).
      const refNum =
        (formData.customer_reference_number || '').trim() || (formData.customer_id || '').trim() || null

      const payload: Record<string, unknown> = {
        customer: selectedCustomerId,
        ship_to_location: selectedShipToId,
        ...(selectedContactId && { contact: selectedContactId }),
        customer_reference_number: refNum,
        customer_name: formData.customer_name,
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
        drop_ship: formData.drop_ship,
        items: soItems.map(item => {
          // Quantity and unit_price must both be in the item's unit_of_measure (backend has no per-line unit).
          const itemObj = items.find(i => i.id === item.item_id)
          const itemUom = (itemObj?.unit_of_measure || 'lbs').toLowerCase()
          const lineUnit = (item.unit || 'lbs').toLowerCase()
          let finalQuantity = typeof item.quantity_ordered === 'string' ? parseFloat(item.quantity_ordered) || 0 : item.quantity_ordered
          let finalUnitPrice = typeof item.unit_price === 'string' ? parseFloat(item.unit_price) || 0 : item.unit_price

          if (itemObj && lineUnit && lineUnit !== itemUom && (lineUnit === 'lbs' || lineUnit === 'kg') && (itemUom === 'lbs' || itemUom === 'kg')) {
            finalQuantity = convertUnit(finalQuantity, lineUnit, itemUom)
            finalUnitPrice = convertPricePerUnit(finalUnitPrice, lineUnit, itemUom)
            finalUnitPrice = Math.round(finalUnitPrice * 100) / 100
          }

          return {
            item_id: item.item_id,
            vendor_part_number: item.vendor_part_number || '',
            description: item.description,
            quantity_ordered: finalQuantity,
            unit_price: finalUnitPrice,
            notes: item.notes || '',
          }
        }),
        // Preserve workflow status on edit; sending 'draft' every time prevented updates from sticking on issued orders.
        status: salesOrder ? salesOrder.status : 'draft',
      }

      if (!salesOrder) {
        if (formData.so_number?.trim()) {
          payload.so_number = formData.so_number.trim()
        }
      } else {
        payload.so_number =
          godModeOn && canUseGodMode && formData.so_number?.trim()
            ? formData.so_number.trim()
            : salesOrder.so_number
      }

      if (godModeOn && canUseGodMode && formData.order_date) {
        payload.order_date = `${formData.order_date}T12:00:00`
      } else {
        delete payload.order_date
      }

      if (salesOrder) {
        // Update existing sales order
        const response = await updateSalesOrder(salesOrder.id, payload as any)
        console.log('Sales order updated successfully:', response)
      } else {
        // Create new sales order
        const response = await createSalesOrder(payload as any)
        console.log('Sales order created successfully:', response)
        const newId = response?.id
        if (newId && pendingPoFile) {
          try {
            await uploadCustomerPo(newId, pendingPoFile)
          } catch (upErr: any) {
            console.error('Failed to attach customer PO PDF:', upErr)
            alert('Sales order was created but the customer PO document could not be attached. You can attach it later when editing the order.')
          }
        }
      }
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error(`Failed to ${salesOrder ? 'update' : 'create'} sales order:`, error)
      const d = error.response?.data
      let msg: string | undefined
      if (typeof d?.detail === 'string') msg = d.detail
      else if (d?.detail && typeof d.detail === 'object') msg = JSON.stringify(d.detail)
      else if (d?.error) msg = typeof d.error === 'string' ? d.error : JSON.stringify(d.error)
      else if (d && typeof d === 'object') msg = JSON.stringify(d)
      alert(msg || error.message || `Failed to ${salesOrder ? 'update' : 'create'} sales order`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-so-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{salesOrder ? 'Edit Sales Order' : 'Create Sales Order from Customer PO'}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          {!salesOrder && (
            <div
              role="button"
              tabIndex={0}
              className={`po-upload-zone ${poUploadDragOver ? 'po-upload-zone--drag-over' : ''} ${poParseLoading ? 'po-upload-zone--loading' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                e.stopPropagation()
                e.dataTransfer.dropEffect = 'copy'
                setPoUploadDragOver(true)
              }}
              onDragLeave={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setPoUploadDragOver(false)
              }}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setPoUploadDragOver(false)
                const file = e.dataTransfer.files?.[0]
                if (file) handlePoFile(file)
              }}
              onClick={() => { if (!poParseLoading && poFileInputRef.current) poFileInputRef.current.click() }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!poParseLoading && poFileInputRef.current) poFileInputRef.current.click() } }}
            >
              <input
                ref={poFileInputRef}
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                className="po-upload-input"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePoFile(f); e.target.value = '' }}
                disabled={poParseLoading}
                aria-hidden
              />
              {poParseLoading ? (
                <span className="po-upload-text">Parsing PO document…</span>
              ) : (
                <>
                  <span className="po-upload-text">Drop customer PO here (PDF or text) or click to upload</span>
                  <span className="po-upload-hint">Auto-fills PO number, customer, address, ship date, and line items</span>
                </>
              )}
              {poParseSuccess && <div className="po-upload-success">{poParseSuccess}</div>}
              {poParseWarning && <div className="po-upload-warning">{poParseWarning}</div>}
              {poExtractedPreview && <details className="po-upload-details"><summary>Extracted text (preview)</summary><pre className="po-upload-pre">{poExtractedPreview}</pre></details>}
              {pendingPoFile && <div className="po-upload-attached">Attached: {pendingPoFile.name} — will be saved with the sales order.</div>}
            </div>
          )}
          {!salesOrder && (
            <div className="so-autofill-help">
              Customer and Item dropdowns only show records already in the system. If the PO customer or products aren’t set up yet, add them in Customers and Customer Pricing first, then create the order (or re-upload the PO). Description, quantity, and unit price from the PO are filled when the parser finds them; select the matching Customer and Item if they don’t auto-select.
            </div>
          )}
          <div className="so-form-section">
            {((!salesOrder) || (godModeOn && canUseGodMode && salesOrder)) && (
              <div className="form-row">
                <div className="form-group">
                  <label>SO Number {salesOrder ? '(God mode)' : '(leave blank for auto-generation)'}</label>
                  <input
                    type="text"
                    value={formData.so_number}
                    onChange={(e) => setFormData({ ...formData, so_number: e.target.value })}
                    placeholder={salesOrder ? 'Edit SO number' : 'e.g. legacy SO-2023-001'}
                  />
                  <small style={{ color: '#666', fontSize: '0.85rem' }}>
                    {salesOrder
                      ? 'Staff only: change the document number when correcting historical data.'
                      : 'For legacy or historical data (God mode), enter the number to use.'}
                  </small>
                </div>
                {godModeOn && canUseGodMode && (!salesOrder || salesOrder.status === 'draft') && (
                  <div className="form-group">
                    <label>Order date</label>
                    <input
                      type="date"
                      value={formData.order_date}
                      onChange={(e) => setFormData({ ...formData, order_date: e.target.value })}
                      max={maxDateForEntry}
                      min={minDateForEntry}
                    />
                  </div>
                )}
              </div>
            )}
            <div className="section-header">
              <h3>Customer Information</h3>
              {salesOrder && customerPoPdfUrl && (
                <a href={customerPoPdfUrl} target="_blank" rel="noopener noreferrer" className="view-customer-po-link">
                  View customer PO (PDF)
                </a>
              )}
            </div>
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
              <div className="form-group form-group--checkbox">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.drop_ship}
                    onChange={(e) => setFormData({ ...formData, drop_ship: e.target.checked })}
                  />
                  <span>Drop ship</span>
                </label>
                <small style={{ color: '#6b7280', display: 'block', marginTop: '0.25rem' }}>
                  Vendor ships direct to this ship-to; you will not receive or allocate warehouse stock for this order.
                </small>
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
              <div className="form-group">
                <label>Contact</label>
                <select
                  value={selectedContactId || ''}
                  onChange={(e) => setSelectedContactId(e.target.value ? parseInt(e.target.value) : null)}
                  disabled={!selectedCustomerId}
                >
                  <option value="">{selectedCustomerId ? 'Select Contact (optional)' : 'Select Customer First'}</option>
                  {contacts.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.first_name} {c.last_name}{c.contact_type ? ` (${String(c.contact_type).charAt(0).toUpperCase() + String(c.contact_type).slice(1)})` : ''}
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
            <div className="section-header so-items-section-header">
              <h3>Items</h3>
              <div className="section-header-actions">
                <div className="unit-toggle">
                  <span className="unit-toggle-label">Quantity in:</span>
                  <button
                    type="button"
                    className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
                    onClick={() => setUnitDisplay('lbs')}
                  >
                    lbs
                  </button>
                  <button
                    type="button"
                    className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
                    onClick={() => setUnitDisplay('kg')}
                  >
                    kg
                  </button>
                </div>
                <button type="button" onClick={addItem} className="btn btn-secondary">+ Add Item</button>
              </div>
            </div>
            
            <table className="so-items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Vendor Part #</th>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit</th>
                  <th title="For lb/kg lines, same display unit as Quantity (use the lbs/kg toggle). Stored per line unit.">Unit price</th>
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
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        value={quantityForDisplay(item)}
                        onChange={(e) => handleQuantityChange(index, e.target.value)}
                        className="number-input"
                        required
                      />
                    </td>
                    <td>
                      {(item.unit || '').toLowerCase() === 'lbs' || (item.unit || '').toLowerCase() === 'kg'
                        ? unitDisplay
                        : (
                            <input
                              type="text"
                              value={item.unit}
                              onChange={(e) => handleItemChange(index, 'unit', e.target.value)}
                              placeholder="e.g. EA"
                            />
                          )}
                    </td>
                    <td>
                      {(item.unit || '').toLowerCase() === 'lbs' || (item.unit || '').toLowerCase() === 'kg' ? (
                        <input
                          type="text"
                          inputMode="decimal"
                          autoComplete="off"
                          value={getUnitPriceInputValue(index, item)}
                          onChange={(e) => handleUnitPriceInputChange(index, e.target.value)}
                          onBlur={() => commitUnitPriceDraftIfNeeded(index)}
                          className="number-input"
                          required
                        />
                      ) : (
                        <input
                          type="text"
                          inputMode="decimal"
                          autoComplete="off"
                          value={item.unit_price === '' || item.unit_price === null || item.unit_price === undefined ? '' : item.unit_price}
                          onChange={(e) => handleItemChange(index, 'unit_price', e.target.value)}
                          className="number-input"
                          required
                        />
                      )}
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
              {loading ? (salesOrder ? 'Updating...' : 'Creating...') : (salesOrder ? 'Update Sales Order' : 'Create Sales Order')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateSalesOrder



