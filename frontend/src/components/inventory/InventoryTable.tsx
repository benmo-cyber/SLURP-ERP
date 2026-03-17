import React, { useState, useEffect } from 'react'
import { getInventoryDetails, getLotsBySkuVendor, updateLot, putLotOnHold, releaseLotFromHold, reconcileLot } from '../../api/inventory'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import { formatNumber, formatNumberFlexible } from '../../utils/formatNumber'
import './InventoryTable.css'

interface InventoryDetail {
  id: string | number
  item_id: number
  item_sku: string
  description: string
  vendor?: string
  pack_size?: number
  pack_size_unit: string
  total_quantity: number
  allocated_to_sales: number
  allocated_to_production: number
  on_hold: number
  on_order: number
  available: number
  quantity_remaining: number
  lot_count?: number
  item_type?: string
  level?: 'sku' | 'vendor'  // Hierarchy level
  vendor_count?: number  // Number of vendors for SKU
  vendors?: InventoryDetail[]  // Nested vendor entries
}

interface Lot {
  id: number
  lot_number: string
  vendor_lot_number?: string
  po_number?: string
  po_tracking_number?: string
  po_carrier?: string
  quantity: number
  quantity_remaining: number
  quantity_on_hold?: number
  received_date: string
  expiration_date?: string
  status: string
  committed_to_sales_qty?: number
  committed_to_production_qty?: number
  pack_size_obj?: {
    id: number
    pack_size: number
    pack_size_unit: string
    description?: string
  }
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
  }
}

function InventoryTable() {
  const [inventoryDetails, setInventoryDetails] = useState<InventoryDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [inventoryTable, setInventoryTable] = useState<'finished_good' | 'raw_material' | 'indirect_material'>('finished_good')
  const [fpsLinks, setFpsLinks] = useState<Map<number, number>>(new Map())
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [lotDetails, setLotDetails] = useState<Map<string, Lot[]>>(new Map())
  const [loadingLots, setLoadingLots] = useState<Set<string>>(new Set())
  const [editingLot, setEditingLot] = useState<{lotId: number, field: 'vendor_lot_number' | 'expiration_date'} | null>(null)
  const [editValue, setEditValue] = useState<string>('')
  const [sortConfig, setSortConfig] = useState<{key: 'description' | 'vendor' | null, direction: 'asc' | 'desc'}>({ key: null, direction: 'asc' })

  useEffect(() => {
    loadData()
  }, [inventoryTable])

  // Reload data when component key changes (refresh trigger)
  useEffect(() => {
    loadData()
  }, []) // This will reload when the component is remounted via key prop

  const handleSort = (key: 'description' | 'vendor') => {
    setSortConfig(prevConfig => ({
      key,
      direction: prevConfig.key === key && prevConfig.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const sortedInventoryDetails = [...inventoryDetails].sort((a, b) => {
    if (!sortConfig.key) return 0
    
    let aValue = ''
    let bValue = ''
    
    if (sortConfig.key === 'description') {
      aValue = a.description?.toLowerCase() || ''
      bValue = b.description?.toLowerCase() || ''
    } else if (sortConfig.key === 'vendor') {
      aValue = (a.vendor || 'zzz').toLowerCase()  // 'zzz' for "All Vendors" to sort last
      bValue = (b.vendor || 'zzz').toLowerCase()
    }
    
    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  useEffect(() => {
    // Load FPS links for finished goods
    loadFpsLinks()
  }, [inventoryDetails])

  const loadData = async () => {
    try {
      setLoading(true)
      console.log('Loading inventory details...')
      const data = await getInventoryDetails(inventoryTable)
      console.log('Inventory data received:', data)
      console.log('Number of entries:', Array.isArray(data) ? data.length : 'Not an array')
      if (Array.isArray(data) && data.length > 0) {
        console.log('First entry:', data[0])
      }
      setInventoryDetails(Array.isArray(data) ? data : [])
    } catch (error: any) {
      console.error('Failed to load inventory:', error)
      console.error('Error response:', error.response?.data)
      console.error('Error status:', error.response?.status)
      // For 500 errors, just set empty data (server will handle gracefully)
      if (error.response?.status === 500) {
        console.error('Server error loading inventory, returning empty data')
        setInventoryDetails([])
      } else {
        // Only show alert for non-500 errors
        alert(`Failed to load inventory data: ${error.message || 'Unknown error'}. Make sure the backend server is running on http://localhost:8000`)
      }
    } finally {
      setLoading(false)
    }
  }

  const loadFpsLinks = async () => {
    // Get unique item IDs for finished goods (from master SKU rows)
    const finishedGoodItemIds = new Set<number>()
    inventoryDetails.forEach(detail => {
      if (detail.item_type === 'finished_good' && detail.level === 'sku') {
        finishedGoodItemIds.add(detail.item_id)
      }
    })

    // Load FPS for each finished good
    const links = new Map<number, number>()
    for (const itemId of finishedGoodItemIds) {
      try {
        const fps = await getFinishedProductSpecification(itemId)
        if (fps && fps.id) {
          links.set(itemId, fps.id)
        }
      } catch (error) {
        // FPS doesn't exist for this item, that's okay
      }
    }
    setFpsLinks(links)
  }

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, unit: string) => {
    let displayValue = quantity
    
    if (unitDisplay === 'kg' && unit === 'lbs') {
      displayValue = quantity * 0.453592
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      displayValue = quantity * 2.20462
    }
    
    // Preserve exact integers when displaying
    // Use tolerance of 0.01 to catch floating point errors (e.g., 615.99 -> 616)
    const roundedToInteger = Math.round(displayValue)
    const isInteger = Math.abs(displayValue - roundedToInteger) <= 0.01
    
    if (isInteger) {
      // Use formatNumberFlexible to show integer without decimals
      return formatNumberFlexible(roundedToInteger, 0, 0)
    } else {
      return formatNumber(displayValue)
    }
  }

  const getDisplayUnit = (unit: string) => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  const toggleSkuExpansion = (sku: string) => {
    const rowKey = `SKU_${sku}`
    const isExpanded = expandedRows.has(rowKey)
    
    if (isExpanded) {
      const newExpanded = new Set(expandedRows)
      newExpanded.delete(rowKey)
      setExpandedRows(newExpanded)
    } else {
      setExpandedRows(new Set([...expandedRows, rowKey]))
    }
  }

  const toggleVendorExpansion = async (detail: InventoryDetail) => {
    const rowKey = `${detail.item_sku}_${detail.vendor}`
    const isExpanded = expandedRows.has(rowKey)
    
    if (isExpanded) {
      // Collapse
      const newExpanded = new Set(expandedRows)
      newExpanded.delete(rowKey)
      setExpandedRows(newExpanded)
    } else {
      // Expand - load lot details
      setExpandedRows(new Set([...expandedRows, rowKey]))
      
      // Check if we already have the lot details
      if (!lotDetails.has(rowKey)) {
        setLoadingLots(new Set([...loadingLots, rowKey]))
        try {
          const lots = await getLotsBySkuVendor(detail.item_sku, detail.vendor)
          setLotDetails(new Map([...lotDetails, [rowKey, lots]]))
        } catch (error) {
          console.error('Failed to load lot details:', error)
        } finally {
          const newLoading = new Set(loadingLots)
          newLoading.delete(rowKey)
          setLoadingLots(newLoading)
        }
      }
    }
  }

  if (loading) {
    return (
      <div className="inventory-table-container">
        <div className="loading">Loading inventory...</div>
      </div>
    )
  }

  return (
    <div className="inventory-table-container">
      <div className="table-controls">
        <div className="unit-toggle">
          <label>Display Units:</label>
          <button
            className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('lbs')}
          >
            lbs
          </button>
          <button
            className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('kg')}
          >
            kg
          </button>
        </div>
        <div className="inventory-table-tabs">
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'finished_good' ? 'active' : ''}`}
            onClick={() => setInventoryTable('finished_good')}
          >
            Finished Goods
          </button>
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'raw_material' ? 'active' : ''}`}
            onClick={() => setInventoryTable('raw_material')}
          >
            Raw Materials
          </button>
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'indirect_material' ? 'active' : ''}`}
            onClick={() => setInventoryTable('indirect_material')}
          >
            Indirect Materials (Packaging)
          </button>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th 
                className="sortable-header"
                onClick={() => handleSort('description')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                Description {sortConfig.key === 'description' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th 
                className="sortable-header"
                onClick={() => handleSort('vendor')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                Vendor {sortConfig.key === 'vendor' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>Pack Size</th>
              <th>Available</th>
              <th>On Order</th>
              <th>Alloc. Sales</th>
              <th>Alloc. Prod</th>
              <th>On Hold</th>
              <th>Lots</th>
            </tr>
          </thead>
          <tbody>
            {sortedInventoryDetails.length === 0 ? (
              <tr>
                <td colSpan={10} className="no-data">No inventory found</td>
              </tr>
            ) : (
              sortedInventoryDetails.map((detail) => {
                // Master SKU row
                if (detail.level === 'sku') {
                  const unit = detail.pack_size_unit
                  const displayAllocSales = unit !== 'ea' ? convertQuantity(detail.allocated_to_sales, unit) : formatNumber(detail.allocated_to_sales, 0)
                  const displayAllocProd = unit !== 'ea' ? convertQuantity(detail.allocated_to_production, unit) : formatNumber(detail.allocated_to_production, 0)
                  const displayOnHold = unit !== 'ea' ? convertQuantity(detail.on_hold, unit) : formatNumber(detail.on_hold, 0)
                  const displayOnOrder = unit !== 'ea' ? convertQuantity(detail.on_order, unit) : formatNumber(detail.on_order, 0)
                  const displayAvailable = unit !== 'ea' ? convertQuantity(detail.available, unit) : formatNumber(detail.available, 0)
                  const displayUnit = getDisplayUnit(unit)

                  const hasFps = fpsLinks.has(detail.item_id) && detail.item_type === 'finished_good'
                  const fpsId = fpsLinks.get(detail.item_id)

                  const skuRowKey = `SKU_${detail.item_sku}`
                  const isSkuExpanded = expandedRows.has(skuRowKey)
                  const vendors = detail.vendors || []

                  return (
                    <React.Fragment key={detail.id}>
                      <tr className={`sku-master-row ${detail.on_hold > 0 ? 'on-hold' : ''}`}>
                        <td>
                          <div className="sku-cell">
                            <span className="sku-master-label">{detail.item_sku}</span>
                            {vendors.length > 0 && (
                              <button
                                className="expand-btn"
                                onClick={() => toggleSkuExpansion(detail.item_sku)}
                                title={isSkuExpanded ? 'Collapse vendor breakdown' : 'Expand vendor breakdown'}
                              >
                                {isSkuExpanded ? '▼' : '▶'}
                              </button>
                            )}
                            {vendors.length > 1 && (
                              <span className="vendor-count-badge">{vendors.length}</span>
                            )}
                          </div>
                        </td>
                        <td>
                          {hasFps && fpsId ? (
                            <a
                              href={getFpsPdfUrl(fpsId)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="fps-link"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {detail.description}
                            </a>
                          ) : (
                            detail.description
                          )}
                        </td>
                        <td>All Vendors</td>
                        <td>-</td>
                        <td className={detail.available > 0 ? 'available' : 'unavailable'}>
                          {displayAvailable} {displayUnit}
                        </td>
                        <td className={detail.on_order > 0 ? 'on-order' : ''}>
                          {displayOnOrder} {displayUnit}
                        </td>
                        <td>{displayAllocSales} {displayUnit}</td>
                        <td>{displayAllocProd} {displayUnit}</td>
                        <td>{displayOnHold} {displayUnit}</td>
                        <td>{detail.lot_count || 0}</td>
                      </tr>
                      {isSkuExpanded && vendors.map((vendorDetail) => {
                        const vendorUnit = vendorDetail.pack_size_unit
                        const vendorDisplayAllocSales = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.allocated_to_sales, vendorUnit) : formatNumber(vendorDetail.allocated_to_sales, 0)
                        const vendorDisplayAllocProd = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.allocated_to_production, vendorUnit) : formatNumber(vendorDetail.allocated_to_production, 0)
                        const vendorDisplayOnHold = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.on_hold, vendorUnit) : formatNumber(vendorDetail.on_hold, 0)
                        const vendorDisplayOnOrder = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.on_order, vendorUnit) : formatNumber(vendorDetail.on_order, 0)
                        const vendorDisplayAvailable = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.available, vendorUnit) : formatNumber(vendorDetail.available, 0)
                        const vendorDisplayUnit = getDisplayUnit(vendorUnit)
                        const vendorPackSizeDisplay = vendorDetail.pack_size ? `${vendorDetail.pack_size} ${vendorUnit}` : '-'

                        const vendorRowKey = `${vendorDetail.item_sku}_${vendorDetail.vendor}`
                        const isVendorExpanded = expandedRows.has(vendorRowKey)
                        const vendorLots = lotDetails.get(vendorRowKey) || []
                        const isLoadingVendorLots = loadingLots.has(vendorRowKey)

                        return (
                          <React.Fragment key={vendorDetail.id}>
                            <tr className={`vendor-row ${vendorDetail.on_hold > 0 ? 'on-hold' : ''}`}>
                              <td>
                                <div className="sku-cell">
                                  <span>↳ {vendorDetail.item_sku}</span>
                                  {vendorDetail.lot_count && vendorDetail.lot_count > 0 && (
                                    <button
                                      className="expand-btn"
                                      onClick={() => toggleVendorExpansion(vendorDetail)}
                                      title={isVendorExpanded ? 'Collapse lot details' : 'Expand lot details'}
                                    >
                                      {isVendorExpanded ? '▼' : '▶'}
                                    </button>
                                  )}
                                </div>
                              </td>
                              <td>{vendorDetail.description}</td>
                              <td>{vendorDetail.vendor}</td>
                              <td>{vendorPackSizeDisplay}</td>
                              <td className={vendorDetail.available > 0 ? 'available' : 'unavailable'}>
                                {vendorDisplayAvailable} {vendorDisplayUnit}
                              </td>
                              <td className={vendorDetail.on_order > 0 ? 'on-order' : ''}>
                                {vendorDisplayOnOrder} {vendorDisplayUnit}
                              </td>
                              <td>{vendorDisplayAllocSales} {vendorDisplayUnit}</td>
                              <td>{vendorDisplayAllocProd} {vendorDisplayUnit}</td>
                              <td>{vendorDisplayOnHold} {vendorDisplayUnit}</td>
                              <td>{vendorDetail.lot_count || 0}</td>
                            </tr>
                            {isVendorExpanded && (
                              <tr className="lot-details-row">
                                <td colSpan={10} className="lot-details-cell">
                                  {isLoadingVendorLots ? (
                                    <div className="loading-lots">Loading lot details...</div>
                                  ) : vendorLots.length === 0 ? (
                                    <div className="no-lots">No lots found</div>
                                  ) : (
                                    <div className="lot-breakdown">
                                      <h4>Lot Breakdown for {vendorDetail.item_sku} - {vendorDetail.vendor}</h4>
                                      <table className="lot-table">
                                        <thead>
                                          <tr>
                                            <th>Vendor Lot #</th>
                                            <th>Internal Lot #</th>
                                            <th>PO Number</th>
                                            <th>Tracking</th>
                                            <th>Pack Size</th>
                                            <th>Received Date</th>
                                            <th>Expiration Date</th>
                                            <th>Quantity</th>
                                            <th>Available</th>
                                            <th>On Hold</th>
                                            <th>Status</th>
                                            <th>Committed</th>
                                            <th>Actions</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {vendorLots.map((lot) => {
                                            const lotUnit = lot.item.unit_of_measure
                                            const displayQty = lotUnit !== 'ea' ? convertQuantity(lot.quantity, lotUnit) : formatNumber(lot.quantity, 0)
                                            const salesCommit = lot.committed_to_sales_qty ?? 0
                                            const prodCommit = lot.committed_to_production_qty ?? 0
                                            const onHold = lot.quantity_on_hold ?? 0
                                            // quantity_remaining from API is already (physical − sales alloc); subtract prod and on hold for available
                                            const availableFromLot = Math.max(0, lot.quantity_remaining - prodCommit - onHold)
                                            const displayRemaining = lotUnit !== 'ea' ? convertQuantity(availableFromLot, lotUnit) : formatNumber(availableFromLot, 0)
                                            const lotDisplayUnit = getDisplayUnit(lotUnit)
                                            const receivedDate = new Date(lot.received_date).toLocaleDateString()
                                            const expDate = lot.expiration_date ? new Date(lot.expiration_date).toLocaleDateString() : 'N/A'
                                            const packSizeDisplay = lot.pack_size_obj 
                                              ? `${lot.pack_size_obj.pack_size} ${lot.pack_size_obj.pack_size_unit}${lot.pack_size_obj.description ? ` (${lot.pack_size_obj.description})` : ''}`
                                              : '-'
                                            
                                            const isEditingVendorLot = editingLot?.lotId === lot.id && editingLot?.field === 'vendor_lot_number'
                                            const isEditingExpDate = editingLot?.lotId === lot.id && editingLot?.field === 'expiration_date'
                                            
                                            const handleFieldClick = (lotId: number, field: 'vendor_lot_number' | 'expiration_date', currentValue: string) => {
                                              setEditingLot({ lotId, field })
                                              if (field === 'expiration_date' && currentValue !== 'N/A') {
                                                // Convert displayed date back to YYYY-MM-DD format for input
                                                const dateObj = new Date(currentValue)
                                                const year = dateObj.getFullYear()
                                                const month = String(dateObj.getMonth() + 1).padStart(2, '0')
                                                const day = String(dateObj.getDate()).padStart(2, '0')
                                                setEditValue(`${year}-${month}-${day}`)
                                              } else {
                                                setEditValue(currentValue === '-' || currentValue === 'N/A' ? '' : currentValue)
                                              }
                                            }
                                            
                                            const handleFieldSave = async () => {
                                              if (!editingLot) return
                                              
                                              try {
                                                const updateData: any = {}
                                                if (editingLot.field === 'vendor_lot_number') {
                                                  updateData.vendor_lot_number = editValue.trim() || null
                                                } else if (editingLot.field === 'expiration_date') {
                                                  updateData.expiration_date = editValue.trim() || null
                                                }
                                                
                                                await updateLot(lot.id, updateData)
                                                
                                                // Update local state
                                                const updatedLots = vendorLots.map(l => 
                                                  l.id === lot.id 
                                                    ? { ...l, ...updateData }
                                                    : l
                                                )
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                
                                                setEditingLot(null)
                                                setEditValue('')
                                              } catch (error) {
                                                console.error('Failed to update lot:', error)
                                                alert('Failed to update lot. Please try again.')
                                              }
                                            }
                                            
                                            const handleFieldCancel = () => {
                                              setEditingLot(null)
                                              setEditValue('')
                                            }
                                            
                                            const handleKeyDown = (e: React.KeyboardEvent) => {
                                              if (e.key === 'Enter') {
                                                handleFieldSave()
                                              } else if (e.key === 'Escape') {
                                                handleFieldCancel()
                                              }
                                            }
                                            
                                            const qtyOnHold = lot.quantity_on_hold ?? 0
                                            const handlePutOnHold = async () => {
                                              const raw = window.prompt(
                                                `Put how much on hold? (Max available from this lot.) Unit: ${lotDisplayUnit}`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty <= 0) {
                                                alert('Enter a positive number.')
                                                return
                                              }
                                              try {
                                                const updated = await putLotOnHold(lot.id, qty)
                                                const updatedLots = vendorLots.map(l => l.id === lot.id ? { ...l, ...updated } : l)
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                console.error('Put on hold failed:', err)
                                                alert(err?.response?.data?.error || 'Failed to put on hold.')
                                              }
                                            }
                                            const handleReleaseFromHold = async () => {
                                              const maxRelease = qtyOnHold
                                              if (maxRelease <= 0) return
                                              const raw = window.prompt(
                                                `Release how much from hold? (Max: ${formatNumber(lotUnit !== 'ea' ? convertQuantity(maxRelease, lotUnit) : maxRelease, 2)} ${lotDisplayUnit})`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty <= 0 || qty > maxRelease) {
                                                alert(`Enter a number between 0 and ${maxRelease}.`)
                                                return
                                              }
                                              try {
                                                const updated = await releaseLotFromHold(lot.id, qty)
                                                const updatedLots = vendorLots.map(l => l.id === lot.id ? { ...l, ...updated } : l)
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                console.error('Release from hold failed:', err)
                                                alert(err?.response?.data?.error || 'Failed to release from hold.')
                                              }
                                            }
                                            const handleReconcile = async () => {
                                              const currentRem = lot.quantity_remaining
                                              const raw = window.prompt(
                                                `Admin reconcile: set quantity remaining (physical) for this lot. Current: ${formatNumber(lotUnit !== 'ea' ? convertQuantity(currentRem, lotUnit) : currentRem, 2)} ${lotDisplayUnit}. New value:`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty < 0) {
                                                alert('Enter a non-negative number.')
                                                return
                                              }
                                              const reason = window.prompt('Reason for reconcile (optional):') || 'Admin reconcile'
                                              const valueInItemUnit = lotUnit === 'ea' ? qty : (unitDisplay === 'kg' && lotUnit === 'lbs' ? qty * 2.20462 : unitDisplay === 'lbs' && lotUnit === 'kg' ? qty / 2.20462 : qty)
                                              try {
                                                const updated = await reconcileLot(lot.id, valueInItemUnit, reason)
                                                const updatedLots = vendorLots.map(l => l.id === lot.id ? { ...l, ...updated } : l)
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                console.error('Reconcile failed:', err)
                                                alert(err?.response?.data?.error || 'Reconcile failed. Requires staff/superuser.')
                                              }
                                            }
                                            
                                            return (
                                              <tr key={lot.id}>
                                                <td 
                                                  className="editable-cell"
                                                  onClick={() => handleFieldClick(lot.id, 'vendor_lot_number', lot.vendor_lot_number || '-')}
                                                  title="Click to edit vendor lot number"
                                                >
                                                  {isEditingVendorLot ? (
                                                    <input
                                                      type="text"
                                                      value={editValue}
                                                      onChange={(e) => setEditValue(e.target.value)}
                                                      onBlur={handleFieldSave}
                                                      onKeyDown={handleKeyDown}
                                                      autoFocus
                                                      className="inline-edit-input"
                                                      onClick={(e) => e.stopPropagation()}
                                                    />
                                                  ) : (
                                                    lot.vendor_lot_number || '-'
                                                  )}
                                                </td>
                                                <td>
                                                  {(() => {
                                                    // For raw materials, vendor lot number is the lot number
                                                    // For finished goods, show internal lot number
                                                    const item = lot.item
                                                    if (item && item.item_type === 'raw_material' && lot.vendor_lot_number) {
                                                      return lot.vendor_lot_number
                                                    }
                                                    return lot.lot_number || '-'
                                                  })()}
                                                </td>
                                                <td>{lot.po_number || '-'}</td>
                                                <td>
                                                  {lot.po_tracking_number ? (
                                                    <span>
                                                      {lot.po_tracking_number}
                                                      {lot.po_carrier && ` (${lot.po_carrier})`}
                                                    </span>
                                                  ) : '-'}
                                                </td>
                                                <td>{packSizeDisplay}</td>
                                                <td>{receivedDate}</td>
                                                <td 
                                                  className="editable-cell"
                                                  onClick={() => handleFieldClick(lot.id, 'expiration_date', expDate)}
                                                  title="Click to edit expiration date"
                                                >
                                                  {isEditingExpDate ? (
                                                    <input
                                                      type="date"
                                                      value={editValue}
                                                      onChange={(e) => setEditValue(e.target.value)}
                                                      onBlur={handleFieldSave}
                                                      onKeyDown={handleKeyDown}
                                                      autoFocus
                                                      className="inline-edit-input"
                                                      onClick={(e) => e.stopPropagation()}
                                                    />
                                                  ) : (
                                                    expDate
                                                  )}
                                                </td>
                                                <td>{displayQty} {lotDisplayUnit}</td>
                                                <td title={`Available = remaining after sales alloc − production (${prodCommit}) − on hold (${onHold})`}>{displayRemaining} {lotDisplayUnit}</td>
                                                <td>
                                                  {(lotUnit !== 'ea' ? convertQuantity(qtyOnHold, lotUnit) : formatNumber(qtyOnHold, 0))} {lotDisplayUnit}
                                                </td>
                                                <td>
                                                  <span className={`status-badge status-${lot.status}`}>
                                                    {lot.status}
                                                  </span>
                                                </td>
                                                <td>
                                                  {(() => {
                                                    const salesQty = lot.committed_to_sales_qty || 0
                                                    const prodQty = lot.committed_to_production_qty || 0
                                                    const lotUnit = lot.item.unit_of_measure
                                                    
                                                    if (salesQty > 0 && prodQty > 0) {
                                                      const displaySalesQty = lotUnit !== 'ea' ? convertQuantity(salesQty, lotUnit) : formatNumber(salesQty, 0)
                                                      const displayProdQty = lotUnit !== 'ea' ? convertQuantity(prodQty, lotUnit) : formatNumber(prodQty, 0)
                                                      return (
                                                        <div className="committed-info">
                                                          <span className="committed-badge committed-sales" title={`Committed to Sales: ${displaySalesQty} ${getDisplayUnit(lotUnit)}`}>
                                                            Sales: {displaySalesQty} {getDisplayUnit(lotUnit)}
                                                          </span>
                                                          <span className="committed-badge committed-production" title={`Committed to Production: ${displayProdQty} ${getDisplayUnit(lotUnit)}`}>
                                                            Prod: {displayProdQty} {getDisplayUnit(lotUnit)}
                                                          </span>
                                                        </div>
                                                      )
                                                    } else if (salesQty > 0) {
                                                      const displayQty = lotUnit !== 'ea' ? convertQuantity(salesQty, lotUnit) : formatNumber(salesQty, 0)
                                                      return (
                                                        <span className="committed-badge committed-sales" title={`Committed to Sales: ${displayQty} ${getDisplayUnit(lotUnit)}`}>
                                                          Sales: {displayQty} {getDisplayUnit(lotUnit)}
                                                        </span>
                                                      )
                                                    } else if (prodQty > 0) {
                                                      const displayQty = lotUnit !== 'ea' ? convertQuantity(prodQty, lotUnit) : formatNumber(prodQty, 0)
                                                      return (
                                                        <span className="committed-badge committed-production" title={`Committed to Production: ${displayQty} ${getDisplayUnit(lotUnit)}`}>
                                                          Prod: {displayQty} {getDisplayUnit(lotUnit)}
                                                        </span>
                                                      )
                                                    } else {
                                                      return <span className="committed-badge not-committed">-</span>
                                                    }
                                                  })()}
                                                </td>
                                                <td>
                                                  {qtyOnHold > 0 && (
                                                    <button
                                                      type="button"
                                                      className="lot-action-btn release-hold"
                                                      onClick={handleReleaseFromHold}
                                                      title="Release from hold (e.g. after micro results)"
                                                    >
                                                      Release from hold
                                                    </button>
                                                  )}
                                                  <button
                                                    type="button"
                                                    className="lot-action-btn put-hold"
                                                    onClick={handlePutOnHold}
                                                    title="Put amount on hold (partial or full)"
                                                  >
                                                    Put on hold
                                                  </button>
                                                  <button
                                                    type="button"
                                                    className="lot-action-btn reconcile-btn"
                                                    onClick={handleReconcile}
                                                    title="Admin override: reconcile quantity to match reality (staff only)"
                                                  >
                                                    Reconcile
                                                  </button>
                                                </td>
                                              </tr>
                                            )
                                          })}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        )
                      })}
                    </React.Fragment>
                  )
                }
                
                // Legacy support: if no level specified, treat as vendor row (backward compatibility)
                return null
              })
            )}
          </tbody>
        </table>
      </div>

      {inventoryDetails.length === 0 && !loading && (
        <div className="empty-state">
          No inventory found. Check in some items to get started.
        </div>
      )}
    </div>
  )
}

export default InventoryTable
