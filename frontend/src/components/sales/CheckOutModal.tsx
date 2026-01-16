import { useState, useEffect } from 'react'
import { getAvailableSalesOrders, getSalesOrder, allocateSalesOrder, shipSalesOrder, cancelSalesOrder } from '../../api/salesOrders'
import { getLotsBySkuVendor, getItems } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './CheckOutModal.css'

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

interface RawMaterialAllocation {
  lot_id: number
  quantity: number
}

interface ItemAllocation {
  item_id: number
  is_distributed: boolean
  allocations: Allocation[]
  raw_materials: RawMaterialAllocation[]
}

interface CheckOutModalProps {
  onClose: () => void
  onSuccess: () => void
}

function CheckOutModal({ onClose, onSuccess }: CheckOutModalProps) {
  console.log('CheckOutModal rendered')
  const [salesOrders, setSalesOrders] = useState<SalesOrder[]>([])
  const [selectedSOId, setSelectedSOId] = useState<number | null>(null)
  const [salesOrder, setSalesOrder] = useState<SalesOrder | null>(null)
  const [loading, setLoading] = useState(false)
  const [availableLots, setAvailableLots] = useState<Map<number, Lot[]>>(new Map())
  const [rawMaterialLots, setRawMaterialLots] = useState<Map<number, Lot[]>>(new Map())
  const [allocations, setAllocations] = useState<Map<number, ItemAllocation>>(new Map())
  const [shipDate, setShipDate] = useState<string>('')
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [saving, setSaving] = useState(false)
  const [shipping, setShipping] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [showBOL, setShowBOL] = useState(false)

  useEffect(() => {
    loadSalesOrders()
  }, [])

  useEffect(() => {
    if (selectedSOId) {
      loadSalesOrder(selectedSOId)
    }
  }, [selectedSOId])

  useEffect(() => {
    if (salesOrder) {
      loadAvailableLots()
      initializeAllocations()
      if (salesOrder.expected_ship_date) {
        const date = new Date(salesOrder.expected_ship_date)
        setShipDate(date.toISOString().split('T')[0])
      } else {
        setShipDate(new Date().toISOString().split('T')[0])
      }
    }
  }, [salesOrder])

  const loadSalesOrders = async () => {
    try {
      setLoading(true)
      console.log('Loading available sales orders...')
      const orders = await getAvailableSalesOrders()
      console.log('Received sales orders:', orders)
      console.log('Number of orders:', orders?.length || 0)
      setSalesOrders(orders || [])
    } catch (error) {
      console.error('Failed to load sales orders:', error)
      alert('Failed to load sales orders')
    } finally {
      setLoading(false)
    }
  }

  const loadSalesOrder = async (id: number) => {
    try {
      setLoading(true)
      const order = await getSalesOrder(id)
      setSalesOrder(order)
    } catch (error) {
      console.error('Failed to load sales order:', error)
      alert('Failed to load sales order')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableLots = async () => {
    if (!salesOrder) return

    // For checkout, we only show lots that are already allocated to this sales order
    const lotsMap = new Map<number, Lot[]>()
    
    for (const soItem of salesOrder.items) {
      // Only show allocated lots for this item
      const allocatedLots: Lot[] = []
      if (soItem.allocated_lots) {
        for (const alloc of soItem.allocated_lots) {
          if (alloc.quantity_allocated > 0 && alloc.lot) {
            allocatedLots.push(alloc.lot)
          }
        }
      }
      lotsMap.set(soItem.id, allocatedLots)
    }

    setAvailableLots(lotsMap)
    setRawMaterialLots(new Map()) // Not used in checkout
  }

  const initializeAllocations = () => {
    if (!salesOrder) return

    // Initialize with quantities to ship (default to all allocated)
    const allocMap = new Map<number, ItemAllocation>()

    for (const item of salesOrder.items) {
      const existingAllocations: Allocation[] = []

      // Start with all allocated quantities as default quantities to ship
      if (item.allocated_lots) {
        for (const alloc of item.allocated_lots) {
          if (alloc.quantity_allocated > 0) {
            existingAllocations.push({
              lot_id: alloc.lot.id,
              quantity: alloc.quantity_allocated // Default to ship all allocated
            })
          }
        }
      }

      allocMap.set(item.id, {
        item_id: item.item.id,
        is_distributed: false, // Not used in checkout
        allocations: existingAllocations,
        raw_materials: []
      })
    }

    setAllocations(allocMap)
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

  const updateRawMaterialAllocation = (itemId: number, lotId: number, quantity: number) => {
    const alloc = allocations.get(itemId)
    if (!alloc) return

    const newAlloc = { ...alloc }
    const existingIndex = newAlloc.raw_materials.findIndex(rm => rm.lot_id === lotId)

    if (quantity > 0) {
      if (existingIndex >= 0) {
        newAlloc.raw_materials[existingIndex].quantity = quantity
      } else {
        newAlloc.raw_materials.push({ lot_id: lotId, quantity })
      }
    } else {
      if (existingIndex >= 0) {
        newAlloc.raw_materials.splice(existingIndex, 1)
      }
    }

    setAllocations(new Map(allocations.set(itemId, newAlloc)))
  }

  const getTotalAllocated = (itemId: number): number => {
    const alloc = allocations.get(itemId)
    if (!alloc) return 0

    if (alloc.is_distributed) {
      return alloc.raw_materials.reduce((sum, rm) => sum + rm.quantity, 0)
    } else {
      return alloc.allocations.reduce((sum, a) => sum + a.quantity, 0)
    }
  }

  const convertQuantity = (quantity: number, unit: string): number => {
    if (unitDisplay === 'kg' && unit === 'lbs') {
      return quantity * 0.453592
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      return quantity * 2.20462
    }
    return quantity
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

  const handleShipOrder = async () => {
    if (!salesOrder || !shipDate) {
      alert('Please select a ship date')
      return
    }

    // Build items array with quantities to ship
    const itemsToShip: Array<{ item_id: number; quantity: number }> = []
    
    for (const item of salesOrder.items) {
      const alloc = allocations.get(item.id)
      if (alloc) {
        const totalToShip = alloc.allocations.reduce((sum, a) => sum + a.quantity, 0)
        if (totalToShip > 0) {
          // Validate we're not shipping more than allocated
          if (totalToShip > item.quantity_allocated) {
            alert(`Cannot ship ${totalToShip} of ${item.item.name}. Only ${item.quantity_allocated} is allocated.`)
            return
          }
          itemsToShip.push({
            item_id: item.id,
            quantity: totalToShip
          })
        }
      }
    }
    
    if (itemsToShip.length === 0) {
      alert('Please select quantities to ship')
      return
    }

    if (!confirm('Are you sure you want to checkout this order? This will create a DRAFT invoice and packing list.')) {
      return
    }

    try {
      setShipping(true)
      const result = await shipSalesOrder(salesOrder.id, {
        ship_date: shipDate,
        items: itemsToShip
      })
      alert('Order checked out successfully! DRAFT invoice created. You can now go to Finance > Invoices to review and issue it.')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to checkout order:', error)
      alert(`Failed to checkout order: ${error.response?.data?.error || error.message}`)
    } finally {
      setShipping(false)
    }
  }

  const handlePrintBOL = async () => {
    if (!salesOrder) return
    
    try {
      // Generate packing list from backend
      const response = await fetch(`http://localhost:8000/api/sales-orders/${salesOrder.id}/packing-list/`, {
        method: 'GET',
        headers: {
          'Accept': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        },
      })
      
      if (!response.ok) {
        throw new Error('Failed to generate packing list')
      }
      
      // Download the file
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Packing_List_${salesOrder.so_number}.docx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error: any) {
      console.error('Failed to generate packing list:', error)
      alert(`Failed to generate packing list: ${error.message}`)
    }
  }

  const handleCancelOrder = async () => {
    if (!salesOrder) return

    if (!confirm('Are you sure you want to cancel this order? This will delete any distributed item lots and reverse all allocations.')) {
      return
    }

    try {
      setCancelling(true)
      await cancelSalesOrder(salesOrder.id)
      alert('Order cancelled successfully')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to cancel order:', error)
      alert(`Failed to cancel order: ${error.response?.data?.error || error.message}`)
    } finally {
      setCancelling(false)
    }
  }

  if (loading && !salesOrder) {
    return (
      <div className="modal-overlay">
        <div className="modal-content">
          <div>Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content checkout-modal">
        <div className="modal-header">
          <h2>Check Out Sales Order</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="checkout-content">
          {/* Step 1: Select Sales Order */}
          <div className="checkout-step">
            <h3>Step 1: Select Sales Order</h3>
            {loading ? (
              <div>Loading sales orders...</div>
            ) : salesOrders.length === 0 ? (
              <div className="warning-text">
                No issued sales orders with allocations available for checkout.
                <br />
                <small>Make sure you have sales orders with status 'issued' that have material allocated.</small>
              </div>
            ) : (
              <>
                <select
                  value={selectedSOId ? String(selectedSOId) : ''}
                  onChange={(e) => {
                    const value = e.target.value
                    console.log('Selected sales order ID:', value)
                    if (value) {
                      const id = parseInt(value, 10)
                      if (!isNaN(id)) {
                        setSelectedSOId(id)
                      } else {
                        setSelectedSOId(null)
                      }
                    } else {
                      setSelectedSOId(null)
                    }
                  }}
                  className="form-select"
                  style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                >
                  <option value="">-- Select Sales Order --</option>
                  {salesOrders.map(so => (
                    <option key={so.id} value={String(so.id)}>
                      {so.so_number} - {so.customer_name} ({so.status})
                    </option>
                  ))}
                </select>
                {process.env.NODE_ENV === 'development' && (
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
                    Debug: {salesOrders.length} sales orders loaded, selected: {selectedSOId || 'none'}
                  </div>
                )}
              </>
            )}
          </div>

          {salesOrder && (
            <>
              {/* Step 2: Allocate Lots */}
              <div className="checkout-step">
                <h3>Step 2: Allocate Inventory</h3>
                {/* Debug info */}
                {process.env.NODE_ENV === 'development' && (
                  <div style={{ fontSize: '12px', color: '#666', marginBottom: '10px' }}>
                    Debug: Sales Order {salesOrder.so_number} has {salesOrder.items.length} items
                  </div>
                )}
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

                {salesOrder.items.map(item => {
                  const alloc = allocations.get(item.id)
                  const totalAllocated = getTotalAllocated(item.id)
                  const remaining = item.quantity_ordered - totalAllocated
                  const isDistributed = item.item.item_type === 'distributed_item'
                  const availableLotsForItem = availableLots.get(item.id) || []
                  const rawMaterialLotsForItem = rawMaterialLots.get(item.id) || []

                  return (
                    <div key={item.id} className="allocation-item">
                      <div className="item-header">
                        <h4>{item.item.name} ({item.item.sku})</h4>
                        <div className="item-stats">
                          <span>Ordered: {formatNumber(convertQuantity(item.quantity_ordered, item.item.unit_of_measure))} {unitDisplay}</span>
                          <span>Allocated: {formatNumber(convertQuantity(item.quantity_allocated, item.item.unit_of_measure))} {unitDisplay}</span>
                          <span>Quantity to Ship: {formatNumber(convertQuantity(totalAllocated, item.item.unit_of_measure))} {unitDisplay}</span>
                        </div>
                      </div>

                      {isDistributed ? (
                        <div className="distributed-item-section">
                          <p className="info-text">
                            <strong>Distributed Item:</strong> Select raw materials. A new lot will be created when you save allocations.
                          </p>
                          <div className="lots-list">
                            {rawMaterialLotsForItem.map(lot => {
                              const rmAlloc = alloc?.raw_materials.find(rm => rm.lot_id === lot.id)
                              const allocatedQty = rmAlloc?.quantity || 0

                              return (
                                <div key={lot.id} className="lot-row">
                                  <div className="lot-info">
                                    <span>{lot.lot_number}</span>
                                    <span>Available: {formatNumber(convertQuantity(lot.quantity_remaining, lot.item.unit_of_measure))} {unitDisplay}</span>
                                    <span>Received: {new Date(lot.received_date).toLocaleDateString()}</span>
                                  </div>
                                  <input
                                    type="number"
                                    min="0"
                                    max={lot.quantity_remaining}
                                    step="0.01"
                                    value={allocatedQty}
                                    onChange={(e) => updateRawMaterialAllocation(
                                      item.id,
                                      lot.id,
                                      parseFloat(e.target.value) || 0
                                    )}
                                    className="quantity-input"
                                  />
                                </div>
                              )
                            })}
                          </div>
                          {rawMaterialLotsForItem.length === 0 && (
                            <p className="warning-text">No raw materials available in inventory</p>
                          )}
                        </div>
                      ) : (
                        <div className="regular-item-section">
                          <div className="lots-list">
                            {availableLotsForItem.map(lot => {
                              const lotAlloc = alloc?.allocations.find(a => a.lot_id === lot.id)
                              const allocatedQty = lotAlloc?.quantity || 0

                              return (
                                <div key={lot.id} className="lot-row">
                                  <div className="lot-info">
                                    <span>{lot.lot_number}</span>
                                    <span>Allocated: {formatNumber(convertQuantity(
                                      item.allocated_lots?.find((a: any) => a.lot.id === lot.id)?.quantity_allocated || 0,
                                      lot.item.unit_of_measure
                                    ))} {unitDisplay}</span>
                                    <span>Received: {new Date(lot.received_date).toLocaleDateString()}</span>
                                    {lot.expiration_date && (
                                      <span>Expires: {new Date(lot.expiration_date).toLocaleDateString()}</span>
                                    )}
                                  </div>
                                  <div className="quantity-input-group">
                                    <label>Quantity to Ship:</label>
                                    <input
                                      type="number"
                                      min="0"
                                      max={maxQty}
                                      step="0.01"
                                      value={allocatedQty}
                                      onChange={(e) => {
                                        const val = parseFloat(e.target.value) || 0
                                        if (val <= maxQty) {
                                          updateAllocation(item.id, lot.id, val)
                                        }
                                      }}
                                      className="quantity-input"
                                    />
                                    <span className="max-hint">(Max: {formatNumber(convertQuantity(maxQty, lot.item.unit_of_measure))} {unitDisplay})</span>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                          {availableLotsForItem.length === 0 && (
                            <p className="warning-text">No lots available for this item</p>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Step 3: Ship Date */}
              <div className="checkout-step">
                <h3>Step 3: Ship Date</h3>
                <div className="form-group">
                  <label>Ship Date *</label>
                  <input
                    type="date"
                    value={shipDate}
                    onChange={(e) => setShipDate(e.target.value)}
                    className="form-input"
                    required
                  />
                  <p className="info-text">You can set the ship date earlier than the requested date if needed.</p>
                </div>
              </div>

              {/* Actions */}
              <div className="checkout-actions">
                <button
                  onClick={handleShipOrder}
                  disabled={shipping || !shipDate}
                  className="btn btn-primary"
                >
                  {shipping ? 'Processing...' : 'Checkout Order & Create Invoice'}
                </button>
                <button
                  onClick={onClose}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default CheckOutModal
