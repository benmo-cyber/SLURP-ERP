import { useState, useEffect } from 'react'
import { getSalesOrder, allocateSalesOrder } from '../../api/salesOrders'
import { getLotsBySkuVendor } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './AllocateModal.css'

interface Lot {
  id: number
  lot_number: string
  quantity_remaining: number
  received_date: string
  expiration_date?: string
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
  }
}

interface SalesOrderItem {
  id: number
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
    item_type: string
    vendor?: string
  }
  quantity_ordered: number
  quantity_allocated: number
  unit_price: number
  allocated_lots?: Array<{
    id: number
    lot: Lot
    quantity_allocated: number
  }>
}

interface SalesOrder {
  id: number
  so_number: string
  customer_name: string
  expected_ship_date: string
  status: string
  items: SalesOrderItem[]
}

interface Allocation {
  lot_id: number
  quantity: number
}

interface ItemAllocation {
  item_id: number
  is_distributed: boolean
  allocations: Allocation[]
  raw_materials: Allocation[]
}

interface AllocateModalProps {
  salesOrderId: number
  onClose: () => void
  onSuccess: () => void
}

function AllocateModal({ salesOrderId, onClose, onSuccess }: AllocateModalProps) {
  const [salesOrder, setSalesOrder] = useState<SalesOrder | null>(null)
  const [loading, setLoading] = useState(false)
  const [availableLots, setAvailableLots] = useState<Map<number, Lot[]>>(new Map())
  const [allocations, setAllocations] = useState<Map<number, ItemAllocation>>(new Map())
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (salesOrderId) {
      loadSalesOrder(salesOrderId)
    }
  }, [salesOrderId])

  useEffect(() => {
    if (salesOrder) {
      loadAvailableLots()
      initializeAllocations()
    }
  }, [salesOrder])

  const loadSalesOrder = async (id: number) => {
    try {
      setLoading(true)
      const data = await getSalesOrder(id)
      setSalesOrder(data)
    } catch (error) {
      console.error('Failed to load sales order:', error)
      alert('Failed to load sales order')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableLots = async () => {
    if (!salesOrder) return

    const lotsMap = new Map<number, Lot[]>()
    
    for (const item of salesOrder.items) {
      try {
        // Get vendor from item if available, otherwise pass undefined
        const vendor = item.item.vendor || undefined
        const lots = await getLotsBySkuVendor(item.item.sku, vendor)
        // Filter lots that are accepted and have remaining quantity
        const available = lots.filter(
          (lot: Lot) => lot.quantity_remaining > 0 && lot.item.id === item.item.id
        )
        lotsMap.set(item.item.id, available)
      } catch (error) {
        console.error(`Failed to load lots for item ${item.item.sku}:`, error)
        lotsMap.set(item.item.id, [])
      }
    }
    
    setAvailableLots(lotsMap)
  }

  const initializeAllocations = () => {
    if (!salesOrder) return

    const newAllocations = new Map<number, ItemAllocation>()
    
    for (const item of salesOrder.items) {
      const existingAllocations: Allocation[] = []
      
      if (item.allocated_lots) {
        for (const alloc of item.allocated_lots) {
          existingAllocations.push({
            lot_id: alloc.lot.id,
            quantity: alloc.quantity_allocated
          })
        }
      }
      
      newAllocations.set(item.id, {
        item_id: item.item.id,
        is_distributed: item.item.item_type === 'distributed',
        allocations: existingAllocations,
        raw_materials: []
      })
    }
    
    setAllocations(newAllocations)
  }

  const updateAllocation = (itemId: number, lotId: number, quantity: number) => {
    const alloc = allocations.get(itemId)
    if (!alloc) return

    const newAlloc = { ...alloc }
    const existingIndex = newAlloc.allocations.findIndex(a => a.lot_id === lotId)
    
    if (quantity > 0) {
      if (existingIndex >= 0) {
        newAlloc.allocations[existingIndex].quantity = quantity
      } else {
        newAlloc.allocations.push({ lot_id: lotId, quantity })
      }
    } else {
      if (existingIndex >= 0) {
        newAlloc.allocations.splice(existingIndex, 1)
      }
    }

    setAllocations(new Map(allocations.set(itemId, newAlloc)))
  }

  const getTotalAllocated = (itemId: number): number => {
    const alloc = allocations.get(itemId)
    if (!alloc) return 0
    return alloc.allocations.reduce((sum, a) => sum + a.quantity, 0)
  }

  /** Convert quantity from given unit to current display unit (for showing in UI). */
  const convertQuantity = (quantity: number, unit: string): number => {
    const u = (unit || '').toLowerCase()
    if (unitDisplay === 'kg' && u === 'lbs') {
      return quantity * 0.453592  // lbs → kg
    }
    if (unitDisplay === 'lbs' && u === 'kg') {
      return quantity * 2.20462  // kg → lbs
    }
    return quantity
  }

  /** Convert value entered in display unit back to lot/item unit for storage and API. */
  const convertDisplayToUnit = (value: number, lotUnit: string): number => {
    const u = (lotUnit || '').toLowerCase()
    if (unitDisplay === 'lbs' && u === 'kg') {
      return value / 2.20462  // user entered lbs → store kg
    }
    if (unitDisplay === 'kg' && u === 'lbs') {
      return value / 0.453592  // user entered kg → store lbs (1/0.453592 = 2.20462)
    }
    return value
  }

  const isFullyAllocated = (item: SalesOrderItem): boolean => {
    const totalAllocated = getTotalAllocated(item.id)
    return totalAllocated >= item.quantity_ordered
  }

  const handleSaveAllocations = async () => {
    if (!salesOrder) return

    try {
      setSaving(true)
      const itemsData: ItemAllocation[] = []

      for (const item of salesOrder.items) {
        const alloc = allocations.get(item.id)
        if (alloc) {
          itemsData.push(alloc)
        }
      }

      await allocateSalesOrder(salesOrder.id, { items: itemsData })
      alert('Allocations saved successfully!')
      await loadSalesOrder(salesOrder.id) // Reload to get updated data
      onSuccess()
    } catch (error: any) {
      console.error('Failed to save allocations:', error)
      alert(`Failed to save allocations: ${error.response?.data?.error || error.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay">
        <div className="allocate-modal">
          <div className="modal-header">
            <h2>Allocate Inventory</h2>
            <button className="close-button" onClick={onClose}>×</button>
          </div>
          <div className="modal-content">
            <div className="loading">Loading sales order...</div>
          </div>
        </div>
      </div>
    )
  }

  if (!salesOrder) {
    return null
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="allocate-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Allocate Inventory - {salesOrder.so_number}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div className="modal-content">
          <div className="so-info">
            <p><strong>Customer:</strong> {salesOrder.customer_name}</p>
            <p><strong>Expected Ship Date:</strong> {salesOrder.expected_ship_date ? new Date(salesOrder.expected_ship_date).toLocaleDateString() : 'Not set'}</p>
          </div>

          <div className="unit-toggle">
            <label>Display Units:</label>
            <button
              className={unitDisplay === 'lbs' ? 'active' : ''}
              onClick={() => setUnitDisplay('lbs')}
            >
              lbs
            </button>
            <button
              className={unitDisplay === 'kg' ? 'active' : ''}
              onClick={() => setUnitDisplay('kg')}
            >
              kg
            </button>
          </div>

          <div className="allocation-items">
            {salesOrder.items.map(item => {
              const lots = availableLots.get(item.item.id) || []
              const alloc = allocations.get(item.id)
              const totalAllocated = getTotalAllocated(item.id)
              const remaining = item.quantity_ordered - totalAllocated
              const unitDisplayText = unitDisplay === 'kg' && item.item.unit_of_measure === 'lbs' ? 'kg' : 
                                     unitDisplay === 'lbs' && item.item.unit_of_measure === 'kg' ? 'lbs' : 
                                     item.item.unit_of_measure
              const isFullyAlloc = isFullyAllocated(item)

              return (
                <div key={item.id} className="allocation-item">
                  <div className="item-header">
                    <h3>{item.item.name} ({item.item.sku})</h3>
                    <div className="item-stats">
                      <span>Ordered: {formatNumber(convertQuantity(item.quantity_ordered, item.item.unit_of_measure))} {unitDisplayText}</span>
                      <span className={isFullyAlloc ? 'fully-allocated' : 'partially-allocated'}>
                        Allocated: {formatNumber(convertQuantity(totalAllocated, item.item.unit_of_measure))} {unitDisplayText}
                      </span>
                      {remaining > 0 && (
                        <span className="remaining">Remaining: {formatNumber(convertQuantity(remaining, item.item.unit_of_measure))} {unitDisplayText}</span>
                      )}
                      {isFullyAlloc && (
                        <span className="fully-allocated-badge">✓ Fully Allocated</span>
                      )}
                    </div>
                  </div>

                  <div className="lots-list">
                    <h4>Available Lots:</h4>
                    {lots.length === 0 ? (
                      <p className="no-lots">No available lots for this item</p>
                    ) : (
                      <table className="lots-table">
                        <thead>
                          <tr>
                            <th>Lot Number</th>
                            <th>Available</th>
                            <th>Allocated</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {lots.map(lot => {
                            const lotAlloc = alloc?.allocations.find(a => a.lot_id === lot.id)
                            const allocatedQty = lotAlloc?.quantity || 0
                            const availableQty = lot.quantity_remaining
                            const maxAllocatable = Math.min(availableQty, remaining + allocatedQty)

                            return (
                              <tr key={lot.id}>
                                <td>{lot.lot_number}</td>
                                <td>{formatNumber(convertQuantity(availableQty, lot.item.unit_of_measure))} {unitDisplayText}</td>
                                <td>
                                  <input
                                    type="number"
                                    min="0"
                                    max={convertQuantity(maxAllocatable, lot.item.unit_of_measure)}
                                    step="0.01"
                                    value={(() => {
                                      const v = convertQuantity(allocatedQty, lot.item.unit_of_measure)
                                      return v === 0 ? 0 : Math.round(v * 100) / 100
                                    })()}
                                    onChange={(e) => {
                                      const val = parseFloat(e.target.value) || 0
                                      const unitQty = convertDisplayToUnit(val, lot.item.unit_of_measure)
                                      updateAllocation(item.id, lot.id, unitQty)
                                    }}
                                    className="allocation-input"
                                  />
                                  <span className="unit-label">{unitDisplayText}</span>
                                </td>
                                <td>
                                  <button
                                    className="btn-allocate-full"
                                    onClick={() => updateAllocation(item.id, lot.id, maxAllocatable)}
                                    disabled={maxAllocatable <= 0}
                                  >
                                    Allocate All
                                  </button>
                                  {allocatedQty > 0 && (
                                    <button
                                      className="btn-clear"
                                      onClick={() => updateAllocation(item.id, lot.id, 0)}
                                    >
                                      Clear
                                    </button>
                                  )}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="modal-actions">
            <button className="btn-cancel" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn-save"
              onClick={handleSaveAllocations}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Allocations'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AllocateModal
