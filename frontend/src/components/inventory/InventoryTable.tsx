import React, { useState, useEffect } from 'react'
import { getInventoryDetails, getLotsBySkuVendor, updateLot } from '../../api/inventory'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import { formatNumber } from '../../utils/formatNumber'
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
  quantity: number
  quantity_remaining: number
  received_date: string
  expiration_date?: string
  status: string
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
  const [fpsLinks, setFpsLinks] = useState<Map<number, number>>(new Map())
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [lotDetails, setLotDetails] = useState<Map<string, Lot[]>>(new Map())
  const [loadingLots, setLoadingLots] = useState<Set<string>>(new Set())
  const [editingLot, setEditingLot] = useState<{lotId: number, field: 'vendor_lot_number' | 'expiration_date'} | null>(null)
  const [editValue, setEditValue] = useState<string>('')

  useEffect(() => {
    loadData()
  }, [])

  // Reload data when component key changes (refresh trigger)
  useEffect(() => {
    loadData()
  }, []) // This will reload when the component is remounted via key prop

  useEffect(() => {
    // Load FPS links for finished goods
    loadFpsLinks()
  }, [inventoryDetails])

  const loadData = async () => {
    try {
      setLoading(true)
      console.log('Loading inventory details...')
      const data = await getInventoryDetails()
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
    if (unitDisplay === 'kg' && unit === 'lbs') {
      return formatNumber(quantity * 0.453592)
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      return formatNumber(quantity * 2.20462)
    }
    return formatNumber(quantity)
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
      </div>

      <div className="table-wrapper">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>SKU</th>
              <th>Description</th>
              <th>Vendor</th>
              <th>Pack Size</th>
              <th>TQ</th>
              <th>Allocated to Sales</th>
              <th>Allocated to Production</th>
              <th>On Hold</th>
              <th>On Order</th>
              <th>Available</th>
              <th>Lots</th>
            </tr>
          </thead>
          <tbody>
            {inventoryDetails.length === 0 ? (
              <tr>
                <td colSpan={12} className="no-data">No inventory found</td>
              </tr>
            ) : (
              inventoryDetails.map((detail) => {
                // Master SKU row
                if (detail.level === 'sku') {
                  const unit = detail.pack_size_unit
                  const displayTQ = unit !== 'ea' ? convertQuantity(detail.total_quantity, unit) : formatNumber(detail.total_quantity, 0)
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
                        <td>{detail.item_id}</td>
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
                              <span className="vendor-count-badge">({vendors.length} vendors)</span>
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
                              <strong>{detail.description}</strong>
                            </a>
                          ) : (
                            <strong>{detail.description}</strong>
                          )}
                        </td>
                        <td>
                          <strong>All Vendors</strong>
                        </td>
                        <td>-</td>
                        <td><strong>{displayTQ} {displayUnit}</strong></td>
                        <td><strong>{displayAllocSales} {displayUnit}</strong></td>
                        <td><strong>{displayAllocProd} {displayUnit}</strong></td>
                        <td><strong>{displayOnHold} {displayUnit}</strong></td>
                        <td><strong>{displayOnOrder} {displayUnit}</strong></td>
                        <td className={detail.available > 0 ? 'available' : 'unavailable'}>
                          <strong>{displayAvailable} {displayUnit}</strong>
                        </td>
                        <td><strong>{detail.lot_count || 0}</strong></td>
                      </tr>
                      {isSkuExpanded && vendors.map((vendorDetail) => {
                        const vendorUnit = vendorDetail.pack_size_unit
                        const vendorDisplayTQ = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.total_quantity, vendorUnit) : formatNumber(vendorDetail.total_quantity, 0)
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
                              <td></td>
                              <td>
                                <div className="sku-cell" style={{ paddingLeft: '1.5rem' }}>
                                  <span style={{ color: '#666' }}>↳ {vendorDetail.item_sku}</span>
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
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDetail.description}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDetail.vendor}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorPackSizeDisplay}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDisplayTQ} {vendorDisplayUnit}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDisplayAllocSales} {vendorDisplayUnit}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDisplayAllocProd} {vendorDisplayUnit}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDisplayOnHold} {vendorDisplayUnit}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDisplayOnOrder} {vendorDisplayUnit}
                              </td>
                              <td className={vendorDetail.available > 0 ? 'available' : 'unavailable'} style={{ paddingLeft: '1.5rem' }}>
                                {vendorDisplayAvailable} {vendorDisplayUnit}
                              </td>
                              <td style={{ paddingLeft: '1.5rem', color: '#666' }}>
                                {vendorDetail.lot_count || 0}
                              </td>
                            </tr>
                            {isVendorExpanded && (
                              <tr className="lot-details-row">
                                <td colSpan={12} className="lot-details-cell" style={{ paddingLeft: '3rem' }}>
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
                                            <th>Pack Size</th>
                                            <th>Received Date</th>
                                            <th>Expiration Date</th>
                                            <th>Quantity</th>
                                            <th>Remaining</th>
                                            <th>Status</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {vendorLots.map((lot) => {
                                            const lotUnit = lot.item.unit_of_measure
                                            const displayQty = lotUnit !== 'ea' ? convertQuantity(lot.quantity, lotUnit) : formatNumber(lot.quantity, 0)
                                            const displayRemaining = lotUnit !== 'ea' ? convertQuantity(lot.quantity_remaining, lotUnit) : formatNumber(lot.quantity_remaining, 0)
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
                                                <td>{displayRemaining} {lotDisplayUnit}</td>
                                                <td>
                                                  <span className={`status-badge status-${lot.status}`}>
                                                    {lot.status}
                                                  </span>
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
