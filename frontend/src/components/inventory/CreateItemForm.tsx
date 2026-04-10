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
  vendor_item_name?: string | null
  vendor_item_number?: string | null
  sku_parent_code?: string | null
  sku_pack_suffix?: string | null
  sku_parent_item?: number | null
}

/** Stem for new pack SKU: parent code from item row, not full SKU (avoids D1307L0040+L0040). */
function parentStemForPackVariant(item: Item): string {
  const code = item.sku_parent_code?.trim()
  if (code) return code.toUpperCase()
  const s = item.sku.trim().toUpperCase()
  const m = s.match(/^(.*)[KL]\d{4}$/i)
  if (m?.[1]) return m[1].toUpperCase()
  return s
}

/** Legacy pigment parent pattern: letter + digits, first digit 1–3, second 3–4 (powder/liquid). */
function validateMasterSkuPattern(sku: string): boolean {
  const s = sku.trim().toUpperCase()
  if (s.length < 5) return false
  if (!/^[A-Z]/.test(s)) return false
  const rest = s.slice(1)
  if (!/^\d+$/.test(rest)) return false
  if (rest.length < 4) return false
  if (!'123'.includes(rest[0])) return false
  if (!'34'.includes(rest[1])) return false
  return true
}

function CreateItemForm({ onClose, onSuccess }: CreateItemFormProps) {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [existingItems, setExistingItems] = useState<Item[]>([])
  const [mode, setMode] = useState<'new' | 'add-vendor'>('new')
  const [selectedItem, setSelectedItem] = useState<Item | null>(null)
  const [formData, setFormData] = useState({
    vendor: '',
    vendor_item_number: '',
    vendor_item_name: '',
    wwi_item_number: '',
    name: '',
    description: '',
    pack_size: '',
    unit_of_measure: 'lbs' as 'lbs' | 'kg' | 'ea',
    price: '',
    item_type: 'raw_material' as 'raw_material' | 'distributed_item' | 'finished_good' | 'indirect_material',
    product_category: '' as string,
    hts_code: '',
    country_of_origin: '',
  })
  const [submitting, setSubmitting] = useState(false)
  /** standard = full SKU string; master = parent code only; variant = pick master + L/K + 4 digits */
  const [skuEntryMode, setSkuEntryMode] = useState<'standard' | 'master' | 'variant'>('standard')
  const [masterItemsList, setMasterItemsList] = useState<Item[]>([])
  const [selectedParentItem, setSelectedParentItem] = useState<Item | null>(null)
  const [packKind, setPackKind] = useState<'L' | 'K'>('L')
  const [packDigits, setPackDigits] = useState('')

  useEffect(() => {
    loadVendors()
    loadExistingItems()
  }, [])

  useEffect(() => {
    if (formData.item_type === 'indirect_material' && skuEntryMode !== 'standard') {
      setSkuEntryMode('standard')
    }
  }, [formData.item_type, skuEntryMode])

  useEffect(() => {
    if (mode !== 'new' || skuEntryMode !== 'variant') return
    let cancelled = false
    getItems({ skuMastersOnly: true })
      .then((data) => {
        if (!cancelled) setMasterItemsList(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setMasterItemsList([])
      })
    return () => {
      cancelled = true
    }
  }, [mode, skuEntryMode])

  useEffect(() => {
    if (mode === 'add-vendor' && selectedItem) {
      // Pre-fill form with selected item data
      setFormData({
        ...formData,
        wwi_item_number: selectedItem.sku,
        name: selectedItem.name,
        vendor_item_name: selectedItem.vendor_item_name || '',
        vendor_item_number: selectedItem.vendor_item_number || '',
        description: selectedItem.description || '',
        item_type: selectedItem.item_type as any,
        product_category: (selectedItem as any).product_category ?? '',
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
        vendor_item_name: '',
        wwi_item_number: '',
        name: '',
        description: '',
        pack_size: '',
        unit_of_measure: 'lbs',
        price: '',
        item_type: 'raw_material',
        product_category: '',
        hts_code: '',
        country_of_origin: '',
      })
      setSelectedItem(null)
      setSkuEntryMode('standard')
      setSelectedParentItem(null)
      setPackDigits('')
      setPackKind('L')
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

    if (!formData.vendor || !formData.name) {
      alert('Please fill in all required fields (Vendor and Name)')
      return
    }

    if (mode === 'new' && formData.item_type !== 'indirect_material') {
      if (skuEntryMode === 'variant') {
        if (!selectedParentItem) {
          alert('Select a parent (master) item for the pack variant.')
          return
        }
        const digits = packDigits.replace(/\D/g, '').padStart(4, '0').slice(0, 4)
        if (!/^\d{4}$/.test(digits)) {
          alert('Pack quantity must be exactly four digits (e.g. 0040 for 40).')
          return
        }
      } else if (!formData.wwi_item_number?.trim()) {
        alert('Please enter the WWI Item Number (SKU).')
        return
      }
    } else if (!formData.wwi_item_number?.trim()) {
      alert('Please fill in all required fields (Vendor, WWI Item Number, and Name)')
      return
    }

    let resolvedSku = formData.wwi_item_number.trim().toUpperCase()
    if (mode === 'new' && formData.item_type !== 'indirect_material' && skuEntryMode === 'variant' && selectedParentItem) {
      const digits = packDigits.replace(/\D/g, '').padStart(4, '0').slice(0, 4)
      resolvedSku = `${selectedParentItem.sku.trim().toUpperCase()}${packKind}${digits}`
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
    if (mode === 'new') {
      const existingNew = existingItems.find(
        (i) => i.sku === resolvedSku && i.vendor === formData.vendor
      )
      if (existingNew) {
        alert(
          `An item with SKU "${resolvedSku}" already exists for vendor ${formData.vendor}.`
        )
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

      let skuForPayload = resolvedSku
      if (mode === 'new' && formData.item_type !== 'indirect_material') {
        if (skuEntryMode === 'master') {
          if (!validateMasterSkuPattern(skuForPayload)) {
            alert(
              'Master SKU should be one letter + material code (legacy: four digits: first 1–3, second 3 powder / 4 liquid).'
            )
            setSubmitting(false)
            return
          }
          if (/[KL]\d{4}$/i.test(skuForPayload)) {
            alert(
              'Master SKU must not include a pack suffix (L or K + four digits). Use "Pack variant" mode to add a pack line.'
            )
            setSubmitting(false)
            return
          }
        }
      }

      payload = {
        sku: skuForPayload,
        name: formData.name,
        vendor_item_name: formData.vendor_item_name || null,
        vendor_item_number: formData.vendor_item_number?.trim() || null,
        description: formData.description || null,
        item_type: formData.item_type,
        product_category: formData.product_category?.trim() || null,
        unit_of_measure: formData.unit_of_measure,
        vendor: formData.vendor || null,
        hts_code: formData.hts_code || null,
        country_of_origin: formData.country_of_origin || null,
      }

      if (mode === 'new' && skuEntryMode === 'variant' && selectedParentItem && formData.item_type !== 'indirect_material') {
        payload.sku_parent_item = selectedParentItem.id
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

  const headerTitle =
    mode === 'add-vendor' ? 'Add another vendor' : 'Create catalog item'
  const headerSubtitle =
    mode === 'add-vendor'
      ? 'Same WWI SKU and name — pick the item, then choose a vendor that is not already on file for it.'
      : 'Define the WWI item number, then who supplies it and how it appears on POs.'

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-item-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{headerTitle}</h2>
            <p className="create-item-subtitle">{headerSubtitle}</p>
          </div>
          <button type="button" onClick={onClose} className="close-btn" aria-label="Close">
            ×
          </button>
        </div>

        <div className="create-item-body">
          <form id="create-item-form" className="create-item-form" onSubmit={handleSubmit}>
          <div className="create-item-section">
            <div className="create-item-section-head">
              <h3 className="create-item-section-title">What are you doing?</h3>
            </div>
            <div className="flow-pick" role="group" aria-label="Create flow">
              <label className={`flow-card ${mode === 'new' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="create-flow"
                  checked={mode === 'new'}
                  onChange={() => setMode('new')}
                />
                <span className="flow-card-title">New item</span>
                <span className="flow-card-desc">A new SKU in the catalog (you will enter or build the WWI number).</span>
              </label>
              <label className={`flow-card ${mode === 'add-vendor' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="create-flow"
                  checked={mode === 'add-vendor'}
                  onChange={() => setMode('add-vendor')}
                />
                <span className="flow-card-title">Another vendor for an existing item</span>
                <span className="flow-card-desc">The SKU already exists — add pricing for a different approved vendor.</span>
              </label>
            </div>
          </div>

          {mode === 'new' && (
            <div className="create-item-section">
              <div className="create-item-section-head">
                <h3 className="create-item-section-title">What kind of item?</h3>
                <p className="create-item-section-lead">This controls how the WWI item number is entered below.</p>
              </div>
              <div className="create-item-panel">
                <div className="form-grid">
                  <div className="form-group">
                    <label htmlFor="item_type">Item type *</label>
                    <select
                      id="item_type"
                      value={formData.item_type}
                      onChange={(e) => setFormData({ ...formData, item_type: e.target.value as any })}
                      required
                    >
                      <option value="raw_material">Raw material</option>
                      <option value="distributed_item">Distributed item</option>
                      <option value="finished_good">Finished good</option>
                      <option value="indirect_material">Indirect material</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="product_category">Product category</label>
                    <select
                      id="product_category"
                      value={formData.product_category || ''}
                      onChange={(e) => setFormData({ ...formData, product_category: e.target.value || '' })}
                    >
                      <option value="">Not set</option>
                      <option value="natural_colors">Natural colors</option>
                      <option value="synthetic_colors">Synthetic colors</option>
                      <option value="antioxidants">Antioxidants</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {mode === 'new' && formData.item_type !== 'indirect_material' && (
            <div className="create-item-section">
              <div className="create-item-section-head">
                <h3 className="create-item-section-title">WWI item number (SKU)</h3>
                <p className="create-item-section-lead">
                  Pick one approach. Indirect materials always use a single full SKU — switch item type below if needed.
                </p>
              </div>
              <div className="create-item-panel">
                <div className="sku-mode-grid" role="radiogroup" aria-label="SKU entry mode">
                  <label className={`sku-mode-card ${skuEntryMode === 'standard' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="sku-entry"
                      checked={skuEntryMode === 'standard'}
                      onChange={() => setSkuEntryMode('standard')}
                    />
                    <div className="sku-mode-card-text">
                      <span className="sku-mode-card-title">Enter the full SKU</span>
                      <span className="sku-mode-card-desc">One field — e.g. D1307L0040 or YM100L0050.</span>
                    </div>
                  </label>
                  <label className={`sku-mode-card ${skuEntryMode === 'master' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="sku-entry"
                      checked={skuEntryMode === 'master'}
                      onChange={() => setSkuEntryMode('master')}
                    />
                    <div className="sku-mode-card-text">
                      <span className="sku-mode-card-title">Master (parent) code only</span>
                      <span className="sku-mode-card-desc">Material line without pack suffix — e.g. D1307. Add pack lines separately.</span>
                    </div>
                  </label>
                  <label className={`sku-mode-card ${skuEntryMode === 'variant' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="sku-entry"
                      checked={skuEntryMode === 'variant'}
                      onChange={() => setSkuEntryMode('variant')}
                    />
                    <div className="sku-mode-card-text">
                      <span className="sku-mode-card-title">Pack line of an existing master</span>
                      <span className="sku-mode-card-desc">Choose the master item, then L or K and four digits (e.g. …L0040).</span>
                    </div>
                  </label>
                </div>

                {skuEntryMode === 'variant' ? (
                  <div className="sku-mode-detail">
                    <div className="form-group full-width" style={{ marginBottom: '0.75rem' }}>
                      <label htmlFor="parent-item">Master item *</label>
                      <select
                        id="parent-item"
                        value={selectedParentItem?.id ?? ''}
                        onChange={(e) => {
                          const id = parseInt(e.target.value, 10)
                          const it = masterItemsList.find((i) => i.id === id)
                          setSelectedParentItem(it ?? null)
                        }}
                        required
                      >
                        <option value="">Select master item…</option>
                        {masterItemsList.map((it) => (
                          <option key={it.id} value={it.id}>
                            {it.sku_parent_code ? `${it.sku_parent_code} · ` : ''}
                            {it.sku} — {it.name}
                            {it.vendor ? ` (${it.vendor})` : ''}
                          </option>
                        ))}
                      </select>
                      <small className="form-hint">
                        One entry per material family (from <code>sku_parent_code</code>). The new SKU is
                        family code + L/K + four digits — not appended to the full SKU you pick. Run{' '}
                        <code>populate_sku_family_fields</code> if the list is empty.
                      </small>
                    </div>
                    <div className="form-group full-width">
                      <label htmlFor="pack_digits">Pack line *</label>
                      <div className="pack-row">
                        <select
                          value={packKind}
                          onChange={(e) => setPackKind(e.target.value as 'L' | 'K')}
                          aria-label="Pack unit L or K"
                        >
                          <option value="L">L (lbs)</option>
                          <option value="K">K (kg)</option>
                        </select>
                        <input
                          id="pack_digits"
                          type="text"
                          inputMode="numeric"
                          maxLength={4}
                          placeholder="0040"
                          value={packDigits}
                          onChange={(e) => setPackDigits(e.target.value.replace(/\D/g, '').slice(0, 4))}
                          required
                          aria-label="Four-digit pack quantity"
                        />
                      </div>
                      <div className="sku-preview-line">
                        Resulting SKU{' '}
                        <code>
                          {selectedParentItem
                            ? `${parentStemForPackVariant(selectedParentItem)}${packKind}${packDigits.replace(/\D/g, '').padStart(4, '0').slice(0, 4)}`
                            : '…'}
                        </code>
                      </div>
                      <small className="form-hint">Four digits for the quantity in that unit (e.g. 0040 → 40).</small>
                    </div>
                  </div>
                ) : (
                  <div className="sku-mode-detail">
                    <div className="form-group full-width">
                      <label htmlFor="wwi_item_number">WWI item number *</label>
                      <input
                        type="text"
                        id="wwi_item_number"
                        value={formData.wwi_item_number}
                        onChange={(e) => setFormData({ ...formData, wwi_item_number: e.target.value })}
                        required
                        placeholder={
                          skuEntryMode === 'master'
                            ? 'e.g. D1307 (parent code only)'
                            : 'e.g. D1307L0040'
                        }
                      />
                      {skuEntryMode === 'master' && (
                        <small className="form-hint">No L/K + four digits here — use &quot;Pack line of an existing master&quot; for that.</small>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {mode === 'new' && formData.item_type === 'indirect_material' && (
            <div className="create-item-section">
              <div className="create-item-section-head">
                <h3 className="create-item-section-title">WWI item number</h3>
                <p className="create-item-section-lead">Indirect materials use one full SKU in a single field.</p>
              </div>
              <div className="create-item-panel">
                <div className="form-group full-width">
                  <label htmlFor="wwi_item_number_indirect">WWI item number *</label>
                  <input
                    type="text"
                    id="wwi_item_number_indirect"
                    value={formData.wwi_item_number}
                    onChange={(e) => setFormData({ ...formData, wwi_item_number: e.target.value })}
                    required
                    placeholder="Full SKU"
                  />
                </div>
              </div>
            </div>
          )}

          {mode === 'add-vendor' && (
            <div className="create-item-section">
              <div className="create-item-section-head">
                <h3 className="create-item-section-title">Which item?</h3>
                <p className="create-item-section-lead">Choose the catalog line to attach this vendor to.</p>
              </div>
              <div className="create-item-panel">
                <div className="form-group full-width" style={{ margin: 0 }}>
                  <label htmlFor="existing-item">Item *</label>
                  <select
                    id="existing-item"
                    value={selectedItem?.id || ''}
                    onChange={(e) => {
                      const item = existingItems.find((i) => i.id === parseInt(e.target.value, 10))
                      if (item) handleItemSelect(item)
                    }}
                    required
                  >
                    <option value="">Select an item…</option>
                    {(() => {
                      const skuMap = new Map<string, Item[]>()
                      existingItems.forEach((item) => {
                        if (!skuMap.has(item.sku)) skuMap.set(item.sku, [])
                        skuMap.get(item.sku)!.push(item)
                      })
                      const sortedSkus = Array.from(skuMap.keys()).sort()
                      return sortedSkus.flatMap((sku) => {
                        const items = skuMap.get(sku)!
                        if (items.length === 1) {
                          const item = items[0]
                          return (
                            <option key={item.id} value={item.id}>
                              {item.sku} — {item.name} {item.vendor ? `(${item.vendor})` : ''}
                            </option>
                          )
                        }
                        const firstItem = items[0]
                        return (
                          <option key={firstItem.id} value={firstItem.id}>
                            {firstItem.sku} — {firstItem.name} ({items.length} vendors)
                          </option>
                        )
                      })
                    })()}
                  </select>
                  {selectedItem && (
                    <div className="selected-item-info">
                      <strong>{selectedItem.sku}</strong> — {selectedItem.name}
                      <br />
                      Vendors already on this SKU:{' '}
                      {existingItems
                        .filter((i) => i.sku === selectedItem.sku && i.vendor)
                        .map((i) => i.vendor)
                        .join(', ') || 'None'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="create-item-section">
            <div className="create-item-section-head">
              <h3 className="create-item-section-title">Vendor &amp; how they list it</h3>
              <p className="create-item-section-lead">Who you buy from and their catalog codes for POs.</p>
            </div>
            <div className="create-item-panel">
              <div className="form-grid">
                <div className="form-group full-width">
                  <label htmlFor="vendor">Vendor *</label>
                  <select
                    id="vendor"
                    value={formData.vendor}
                    onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
                    required
                    disabled={vendors.length === 0}
                  >
                    <option value="">
                      {vendors.length === 0 ? 'No approved vendors available' : 'Select vendor'}
                    </option>
                    {(() => {
                      if (mode === 'add-vendor' && formData.wwi_item_number) {
                        const existingVendors = existingItems
                          .filter((i) => i.sku === formData.wwi_item_number && i.vendor)
                          .map((i) => i.vendor)
                        return vendors
                          .filter((v) => !existingVendors.includes(v.name))
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
                      .filter((i) => i.sku === formData.wwi_item_number && i.vendor)
                      .map((i) => i.vendor)
                    if (existingVendors.length > 0) {
                      return (
                        <small className="form-hint form-hint-info">
                          Already on file for this SKU: {existingVendors.join(', ')}
                        </small>
                      )
                    }
                    return null
                  })()}
                  {vendors.length === 0 && (
                    <small className="form-hint form-hint-warn">
                      Approve vendors in Quality before creating items.
                    </small>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="vendor_item_number">Vendor item #</label>
                  <input
                    type="text"
                    id="vendor_item_number"
                    value={formData.vendor_item_number || ''}
                    onChange={(e) => setFormData({ ...formData, vendor_item_number: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="vendor_item_name">Vendor item name</label>
                  <input
                    type="text"
                    id="vendor_item_name"
                    value={formData.vendor_item_name || ''}
                    onChange={(e) => setFormData({ ...formData, vendor_item_name: e.target.value })}
                    placeholder="Optional — defaults to WWI name on POs"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="create-item-section">
            <div className="create-item-section-head">
              <h3 className="create-item-section-title">WWI name &amp; notes</h3>
            </div>
            <div className="create-item-panel">
              <div className="form-grid">
                <div className="form-group full-width">
                  <label htmlFor="name">WWI item name *</label>
                  <input
                    type="text"
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    disabled={mode === 'add-vendor'}
                  />
                  {mode === 'add-vendor' && (
                    <span className="field-lock-note">Locked — same as the selected catalog item.</span>
                  )}
                </div>

                <div className="form-group full-width">
                  <label htmlFor="description">Description</label>
                  <textarea
                    id="description"
                    rows={3}
                    value={formData.description || ''}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
                </div>

                {mode === 'add-vendor' && (
                  <>
                    <div className="form-group full-width">
                      <label>Item type</label>
                      <input
                        type="text"
                        readOnly
                        value={
                          {
                            raw_material: 'Raw material',
                            distributed_item: 'Distributed item',
                            finished_good: 'Finished good',
                            indirect_material: 'Indirect material',
                          }[formData.item_type] || formData.item_type
                        }
                        className="readonly-field"
                      />
                      <span className="field-lock-note">From the catalog item you selected.</span>
                    </div>
                    <div className="form-group full-width">
                      <label htmlFor="product_category_av">Product category</label>
                      <select
                        id="product_category_av"
                        value={formData.product_category || ''}
                        onChange={(e) => setFormData({ ...formData, product_category: e.target.value || '' })}
                      >
                        <option value="">Not set</option>
                        <option value="natural_colors">Natural colors</option>
                        <option value="synthetic_colors">Synthetic colors</option>
                        <option value="antioxidants">Antioxidants</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="create-item-section">
            <div className="create-item-section-head">
              <h3 className="create-item-section-title">Pack &amp; price</h3>
              <p className="create-item-section-lead">Optional — add now or later.</p>
            </div>
            <div className="create-item-panel">
              <div className="form-grid">
                <div className="form-group">
                  <label htmlFor="pack_size">Pack size</label>
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
                      onChange={(e) =>
                        setFormData({ ...formData, unit_of_measure: e.target.value as 'lbs' | 'kg' | 'ea' })
                      }
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
                    <span className="unit-label">per {formData.unit_of_measure}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {(formData.item_type === 'raw_material' || formData.item_type === 'distributed_item') && (
            <div className="create-item-section">
              <details className="create-item-details">
                <summary>Import &amp; tariff (optional)</summary>
                <div className="details-inner">
                  <div className="form-grid">
                    <div className="form-group">
                      <label htmlFor="hts_code">HTS code</label>
                      <input
                        type="text"
                        id="hts_code"
                        value={formData.hts_code || ''}
                        onChange={(e) => setFormData({ ...formData, hts_code: e.target.value })}
                        placeholder="Tariff schedule code"
                      />
                      <small className="form-hint">Flexport tariff lookup</small>
                    </div>

                    <div className="form-group">
                      <label htmlFor="country_of_origin">Country of origin</label>
                      <input
                        type="text"
                        id="country_of_origin"
                        value={formData.country_of_origin || ''}
                        onChange={(e) => setFormData({ ...formData, country_of_origin: e.target.value })}
                        placeholder="e.g. United States"
                      />
                    </div>
                  </div>
                </div>
              </details>
            </div>
          )}

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || (mode === 'add-vendor' && !selectedItem)}
            >
              {submitting
                ? mode === 'add-vendor'
                  ? 'Adding…'
                  : 'Creating…'
                : mode === 'add-vendor'
                  ? 'Add vendor line'
                  : 'Create item'}
            </button>
          </div>
        </form>
        </div>
      </div>
    </div>
  )
}

export default CreateItemForm

