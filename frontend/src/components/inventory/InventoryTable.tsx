import React, { useState, useEffect } from 'react'
import { getInventoryDetails, getLotsBySkuVendor } from '../../api/inventory'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import './InventoryTable.css'

interface InventoryDetail {
  id: string | number
  item_id: number
  item_sku: string
  description: string
  vendor: string
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
}

interface Lot {
  id: number
  lot_number: string
  quantity: number
  quantity_remaining: number
  received_date: string
  expiration_date?: string
  status: string
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

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    // Load FPS links for finished goods
    loadFpsLinks()
  }, [inventoryDetails])

  const loadData = async () => {
    try {
      setLoading(true)
      const data = await getInventoryDetails()
      setInventoryDetails(data)
    } catch (error) {
      console.error('Failed to load inventory:', error)
      alert('Failed to load inventory data. Make sure the backend server is running.')
    } finally {
      setLoading(false)
    }
  }

  const loadFpsLinks = async () => {
    // Get unique item IDs for finished goods
    const finishedGoodItemIds = new Set<number>()
    inventoryDetails.forEach(detail => {
      if (detail.item_type === 'finished_good') {
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
      return (quantity * 0.453592).toFixed(2)
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      return (quantity * 2.20462).toFixed(2)
    }
    return quantity.toFixed(2)
  }

  const getDisplayUnit = (unit: string) => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  const toggleRowExpansion = async (detail: InventoryDetail) => {
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
                const unit = detail.pack_size_unit
                const displayTQ = unit !== 'ea' ? convertQuantity(detail.total_quantity, unit) : detail.total_quantity.toFixed(0)
                const displayAllocSales = unit !== 'ea' ? convertQuantity(detail.allocated_to_sales, unit) : detail.allocated_to_sales.toFixed(0)
                const displayAllocProd = unit !== 'ea' ? convertQuantity(detail.allocated_to_production, unit) : detail.allocated_to_production.toFixed(0)
                const displayOnHold = unit !== 'ea' ? convertQuantity(detail.on_hold, unit) : detail.on_hold.toFixed(0)
                const displayOnOrder = unit !== 'ea' ? convertQuantity(detail.on_order, unit) : detail.on_order.toFixed(0)
                const displayAvailable = unit !== 'ea' ? convertQuantity(detail.available, unit) : detail.available.toFixed(0)
                const displayUnit = getDisplayUnit(unit)
                const packSizeDisplay = detail.pack_size ? `${detail.pack_size} ${unit}` : '-'

                const hasFps = fpsLinks.has(detail.item_id) && detail.item_type === 'finished_good'
                const fpsId = fpsLinks.get(detail.item_id)

                const rowKey = `${detail.item_sku}_${detail.vendor}`
                const isExpanded = expandedRows.has(rowKey)
                const lots = lotDetails.get(rowKey) || []
                const isLoadingLots = loadingLots.has(rowKey)

                return (
                  <React.Fragment key={detail.id}>
                    <tr className={detail.on_hold > 0 ? 'on-hold' : ''}>
                      <td>{detail.item_id}</td>
                      <td>
                        <div className="sku-cell">
                          <span>{detail.item_sku}</span>
                          {detail.lot_count && detail.lot_count > 0 && (
                            <button
                              className="expand-btn"
                              onClick={() => toggleRowExpansion(detail)}
                              title={isExpanded ? 'Collapse lot details' : 'Expand lot details'}
                            >
                              {isExpanded ? '▼' : '▶'}
                            </button>
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
                      <td>{detail.vendor}</td>
                      <td>{packSizeDisplay}</td>
                      <td>{displayTQ} {displayUnit}</td>
                      <td>{displayAllocSales} {displayUnit}</td>
                      <td>{displayAllocProd} {displayUnit}</td>
                      <td>{displayOnHold} {displayUnit}</td>
                      <td>{displayOnOrder} {displayUnit}</td>
                      <td className={detail.available > 0 ? 'available' : 'unavailable'}>
                        {displayAvailable} {displayUnit}
                      </td>
                      <td>{detail.lot_count || 0}</td>
                    </tr>
                    {isExpanded && (
                      <tr className="lot-details-row">
                        <td colSpan={12} className="lot-details-cell">
                          {isLoadingLots ? (
                            <div className="loading-lots">Loading lot details...</div>
                          ) : lots.length === 0 ? (
                            <div className="no-lots">No lots found</div>
                          ) : (
                            <div className="lot-breakdown">
                              <h4>Lot Breakdown for {detail.item_sku} - {detail.vendor}</h4>
                              <table className="lot-table">
                                <thead>
                                  <tr>
                                    <th>Lot Number</th>
                                    <th>Received Date</th>
                                    <th>Expiration Date</th>
                                    <th>Quantity</th>
                                    <th>Remaining</th>
                                    <th>Status</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {lots.map((lot) => {
                                    const lotUnit = lot.item.unit_of_measure
                                    const displayQty = lotUnit !== 'ea' ? convertQuantity(lot.quantity, lotUnit) : lot.quantity.toFixed(0)
                                    const displayRemaining = lotUnit !== 'ea' ? convertQuantity(lot.quantity_remaining, lotUnit) : lot.quantity_remaining.toFixed(0)
                                    const lotDisplayUnit = getDisplayUnit(lotUnit)
                                    const receivedDate = new Date(lot.received_date).toLocaleDateString()
                                    const expDate = lot.expiration_date ? new Date(lot.expiration_date).toLocaleDateString() : 'N/A'
                                    
                                    return (
                                      <tr key={lot.id}>
                                        <td>{lot.lot_number}</td>
                                        <td>{receivedDate}</td>
                                        <td>{expDate}</td>
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
