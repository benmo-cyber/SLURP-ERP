import { useState, useEffect, useRef } from 'react'
import { getAvailableSalesOrders, getSalesOrder, allocateSalesOrder, shipSalesOrder, cancelSalesOrder } from '../../api/salesOrders'
import { formatNumber } from '../../utils/formatNumber'
import { formatAppDate } from '../../utils/appDateFormat'
import { useGodMode } from '../../context/GodModeContext'
import './CheckOutModal.css'

interface Lot {
  id: number
  lot_number: string
  quantity_remaining: number
  received_date: string
  expiration_date?: string
  status?: string
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

/** Mass qty in native UoM (lbs/kg): 2 decimals to avoid float junk like 499.99899752 in inputs. */
function roundMassInNativeUnit(qty: number, unitOfMeasure: string): number {
  const u = (unitOfMeasure || '').toLowerCase()
  if (u === 'ea') return Math.round(qty)
  if (u !== 'lbs' && u !== 'kg') return qty
  return Math.round(qty * 100) / 100
}

/** If qty is within tolerance of max (allocation drift), snap to max so "ship all" shows 500 not 499.998… */
function snapShipQtyToMax(qty: number, maxQty: number, unitOfMeasure: string): number {
  const q = roundMassInNativeUnit(qty, unitOfMeasure)
  const m = roundMassInNativeUnit(maxQty, unitOfMeasure)
  const u = (unitOfMeasure || '').toLowerCase()
  const tol = u === 'ea' ? 0.51 : 0.015
  if (Math.abs(q - m) <= tol) return m
  return q
}

function CheckOutModal({ onClose, onSuccess }: CheckOutModalProps) {
  const { maxDateForEntry } = useGodMode()
  const [salesOrders, setSalesOrders] = useState<SalesOrder[]>([])
  const [selectedSOId, setSelectedSOId] = useState<number | null>(null)
  const [salesOrder, setSalesOrder] = useState<SalesOrder | null>(null)
  const [loading, setLoading] = useState(false)
  const [availableLots, setAvailableLots] = useState<Map<number, Lot[]>>(new Map())
  const [rawMaterialLots, setRawMaterialLots] = useState<Map<number, Lot[]>>(new Map())
  const [allocations, setAllocations] = useState<Map<number, ItemAllocation>>(new Map())
  const [shipDate, setShipDate] = useState<string>('')
  const [carrier, setCarrier] = useState<string>('')
  const [trackingNumber, setTrackingNumber] = useState<string>('')
  const [pieces, setPieces] = useState<number | ''>('')
  const [pieceDimensions, setPieceDimensions] = useState<string[]>([])
  const [pieceWeights, setPieceWeights] = useState<string[]>([])
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [saving, setSaving] = useState(false)
  const [shipping, setShipping] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const shipSubmitLock = useRef(false)

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

  useEffect(() => {
    if (pieces === '' || typeof pieces !== 'number' || pieces < 1) {
      setPieceDimensions([])
      setPieceWeights([])
      return
    }
    const n = pieces
    setPieceDimensions((prev) => {
      const next = prev.slice(0, n)
      while (next.length < n) next.push('')
      return next
    })
    setPieceWeights((prev) => {
      const next = prev.slice(0, n)
      while (next.length < n) next.push('')
      return next
    })
  }, [pieces])

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
    if (shipSubmitLock.current) return
    if (!salesOrder || !shipDate) {
      alert('Please select a ship date')
      return
    }

    // Build items array with quantities to ship
    const itemsToShip: Array<{ item_id: number; quantity: number }> = []
    
    for (const item of salesOrder.items) {
      const alloc = allocations.get(item.id)
      if (alloc) {
        const rawSum = alloc.allocations.reduce((sum, a) => sum + a.quantity, 0)
        const totalToShip = roundMassInNativeUnit(rawSum, item.item.unit_of_measure)
        if (totalToShip > 0) {
          const allocCap = roundMassInNativeUnit(item.quantity_allocated, item.item.unit_of_measure)
          if (totalToShip > allocCap + 0.02) {
            alert(`Cannot ship ${totalToShip} of ${item.item.name}. Only ${item.quantity_allocated} is allocated.`)
            return
          }
          itemsToShip.push({
            item_id: item.id,
            quantity: snapShipQtyToMax(totalToShip, allocCap, item.item.unit_of_measure),
          })
        }
      }
    }
    
    if (itemsToShip.length === 0) {
      alert('Please select quantities to ship')
      return
    }

    const itemIdsToShip = new Set(itemsToShip.map((i: { item_id: number }) => i.item_id))
    const hasOnHoldAllocated = salesOrder?.items?.some(
      (item) => itemIdsToShip.has(item.item.id) && item.allocated_lots?.some(
        (al: { lot: Lot }) => al.lot?.status === 'on_hold'
      )
    )
    if (hasOnHoldAllocated && !confirm('One or more allocated lots are on hold (ship under quarantine). Proceed with checkout?')) {
      return
    }

    if (!carrier.trim()) {
      alert('Carrier is required (printed on the packing list and invoice).')
      return
    }
    if (pieces === '' || typeof pieces !== 'number' || pieces < 1) {
      alert('Enter the number of pieces (boxes, pallets, etc.) for this shipment.')
      return
    }
    const pieceCount = pieces
    if (pieceDimensions.length !== pieceCount || pieceWeights.length !== pieceCount) {
      alert('Dimension and weight fields must match the number of pieces.')
      return
    }
    for (let i = 0; i < pieceCount; i++) {
      if (!pieceDimensions[i]?.trim()) {
        alert(`Enter dimensions for piece ${i + 1} (e.g. L×W×H).`)
        return
      }
      if (!pieceWeights[i]?.trim()) {
        alert(`Enter weight for piece ${i + 1} (include unit, e.g. 45 lbs).`)
        return
      }
    }

    if (!confirm('Are you sure you want to checkout this order? This will create a DRAFT invoice and save packing list details.')) {
      return
    }

    shipSubmitLock.current = true
    const idempotencyKey =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`
    try {
      setShipping(true)
      await shipSalesOrder(
        salesOrder.id,
        {
          ship_date: shipDate,
          items: itemsToShip,
          carrier: carrier.trim(),
          tracking_number: trackingNumber.trim() || undefined,
          pieces: pieceCount,
          piece_dimensions: pieceDimensions.map((d) => d.trim()),
          piece_weights: pieceWeights.map((w) => w.trim()),
        },
        { idempotencyKey }
      )
      alert('Order checked out successfully! DRAFT invoice created. You can now go to Finance > Invoices to review and issue it.')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to checkout order:', error)
      alert(`Failed to checkout order: ${error.response?.data?.error || error.message}`)
    } finally {
      setShipping(false)
      shipSubmitLock.current = false
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
              </>
            )}
          </div>

          {salesOrder && (
            <>
              {/* Step 2: Show allocated lots and enter quantity to ship today (supports partial shipments) */}
              <div className="checkout-step">
                <h3>Step 2: Allocated lots & quantity to ship today</h3>
                <p className="info-text" style={{ marginBottom: '12px' }}>
                  Below are the lots allocated to this sales order. Enter the amount you are shipping today from each lot (e.g. ship the rest on another date).
                </p>
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

                      {availableLotsForItem.length > 0 ? (
                        <div className="allocated-lots-section">
                          <div className="lots-list">
                            {availableLotsForItem.map(lot => {
                              const lotAlloc = alloc?.allocations.find(a => a.lot_id === lot.id)
                              const quantityToShip = roundMassInNativeUnit(
                                lotAlloc?.quantity ?? 0,
                                lot.item.unit_of_measure
                              )
                              const allocatedToThisSO = item.allocated_lots?.find((a: any) => a.lot.id === lot.id)?.quantity_allocated ?? 0
                              const maxQty = allocatedToThisSO

                              return (
                                <div key={lot.id} className="lot-row">
                                  <div className="lot-info">
                                    <span><strong>Lot:</strong> {lot.lot_number}</span>
                                    <span>Allocated to this order: {formatNumber(convertQuantity(allocatedToThisSO, lot.item.unit_of_measure))} {unitDisplay}</span>
                                    <span>Received: {formatAppDate(lot.received_date)}</span>
                                    {lot.expiration_date && (
                                      <span>Expires: {formatAppDate(lot.expiration_date)}</span>
                                    )}
                                  </div>
                                  <div className="quantity-input-group">
                                    <label>Quantity to ship today:</label>
                                    <input
                                      type="number"
                                      min="0"
                                      max={maxQty}
                                      step="0.01"
                                      value={quantityToShip}
                                      onChange={(e) => {
                                        const val = parseFloat(e.target.value) || 0
                                        const clamped = Math.min(Math.max(0, val), maxQty)
                                        updateAllocation(
                                          item.id,
                                          lot.id,
                                          snapShipQtyToMax(clamped, maxQty, lot.item.unit_of_measure)
                                        )
                                      }}
                                      className="quantity-input"
                                    />
                                    <span className="max-hint">(Max: {formatNumber(convertQuantity(maxQty, lot.item.unit_of_measure))} {unitDisplay})</span>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      ) : isDistributed ? (
                        <div className="distributed-item-section">
                          <p className="info-text">
                            <strong>Distributed item:</strong> No lots allocated yet. Allocate this item from the sales order list first, then return to Check Out.
                          </p>
                        </div>
                      ) : (
                        <p className="warning-text">No lots allocated for this item.</p>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Step 3: Ship Date & shipping details (for packing list) */}
              <div className="checkout-step">
                <h3>Step 3: Ship Date & shipping details</h3>
                <p className="info-text" style={{ marginBottom: '12px' }}>
                  Carrier, piece count, and dimensions plus weight for each piece are required and are printed on the packing list after checkout. Tracking is optional and can be added later.
                </p>
                <div className="form-group">
                  <label>Ship Date *</label>
                  <input
                    type="date"
                    value={shipDate}
                    onChange={(e) => setShipDate(e.target.value)}
                    className="form-input"
                    max={maxDateForEntry}
                    required
                  />
                  <p className="info-text">You can set the ship date earlier than the requested date if needed.</p>
                </div>
                <div className="form-group">
                  <label>Carrier *</label>
                  <input
                    type="text"
                    value={carrier}
                    onChange={(e) => setCarrier(e.target.value)}
                    placeholder="e.g. FedEx, UPS"
                    className="form-input"
                  />
                  <p className="info-text">Shown on the packing list and invoice (SHIPPED VIA).</p>
                </div>
                <div className="form-group">
                  <label>Tracking number</label>
                  <input
                    type="text"
                    value={trackingNumber}
                    onChange={(e) => setTrackingNumber(e.target.value)}
                    placeholder="Optional — add when available"
                    className="form-input"
                  />
                  <p className="info-text">If blank, you can add tracking on the sales order or before issuing the invoice.</p>
                </div>
                <div className="form-group">
                  <label>Pieces *</label>
                  <input
                    type="number"
                    min={1}
                    value={pieces === '' ? '' : pieces}
                    onChange={(e) => {
                      const v = e.target.value
                      if (v === '') {
                        setPieces('')
                        return
                      }
                      const n = parseInt(v, 10)
                      setPieces(Number.isNaN(n) ? '' : Math.max(1, n))
                    }}
                    placeholder="Number of handling units (boxes, pallets, etc.)"
                    className="form-input"
                  />
                  <p className="info-text">
                    How many separate cartons or pallets for <strong>this checkout</strong>. Partial shipments use a separate checkout with their own pieces and dimensions. After checkout, open the packing list from Sales Orders (Pack list or Release).
                  </p>
                </div>
                {typeof pieces === 'number' && pieces >= 1 && (
                  <div className="form-group piece-dimensions-block">
                    <label className="piece-dimensions-heading">Dimensions &amp; weight * (one row per piece)</label>
                    <p className="info-text">Enter size and weight for each handling unit.</p>
                    {Array.from({ length: pieces }, (_, idx) => (
                      <div key={idx} className="piece-handling-unit">
                        <div className="piece-handling-unit-title">Piece {idx + 1}</div>
                        <div className="piece-handling-unit-fields">
                          <div className="piece-field">
                            <label htmlFor={`piece-dim-${idx}`}>Dimensions</label>
                            <input
                              id={`piece-dim-${idx}`}
                              type="text"
                              value={pieceDimensions[idx] ?? ''}
                              onChange={(e) => {
                                const val = e.target.value
                                setPieceDimensions((prev) => {
                                  const copy = [...prev]
                                  while (copy.length < pieces) copy.push('')
                                  copy[idx] = val
                                  return copy
                                })
                              }}
                              placeholder="e.g. 48×40×60 in"
                              className="form-input"
                              autoComplete="off"
                            />
                          </div>
                          <div className="piece-field">
                            <label htmlFor={`piece-wt-${idx}`}>Weight</label>
                            <input
                              id={`piece-wt-${idx}`}
                              type="text"
                              value={pieceWeights[idx] ?? ''}
                              onChange={(e) => {
                                const val = e.target.value
                                setPieceWeights((prev) => {
                                  const copy = [...prev]
                                  while (copy.length < pieces) copy.push('')
                                  copy[idx] = val
                                  return copy
                                })
                              }}
                              placeholder="e.g. 45 lbs"
                              className="form-input"
                              autoComplete="off"
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
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
