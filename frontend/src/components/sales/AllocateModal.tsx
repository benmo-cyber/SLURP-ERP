import { useState, useEffect } from 'react'
import { getSalesOrder, allocateSalesOrder } from '../../api/salesOrders'
import { getLotsBySkuVendor } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import { lotAvailableForUse } from '../../utils/lotQuantities'
import { formatAppDate } from '../../utils/appDateFormat'
import './AllocateModal.css'

interface Lot {
  id: number
  lot_number: string
  quantity_remaining: number
  quantity_available_for_use?: number
  quantity_on_hold?: number
  committed_to_production_qty?: number
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
    vendor?: string
  }
  quantity_ordered: number
  quantity_allocated: number
  unit_price: number
  allocated_lots?: Array<{
    id: number
    lot: Lot
    quantity_allocated: number
    coa_customer_pdf_url?: string | null
  }>
}

interface SalesOrder {
  id: number
  so_number: string
  customer_name: string
  expected_ship_date: string
  status: string
  items: SalesOrderItem[]
  drop_ship?: boolean
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

function normalizeSku(s: string): string {
  return (s || '').trim().toUpperCase()
}

/**
 * Inventory API often returns no "available" lots when stock is depleted, on hold (without toggle),
 * or filtered — but this SO may still have allocations. Merge those lots in so quantities can be
 * cleared (re-allocate / unallocate).
 */
function placeholderLot(item: SalesOrderItem, lotId: number): Lot {
  return {
    id: lotId,
    lot_number: `Lot #${lotId}`,
    quantity_remaining: 0,
    received_date: '',
    item: {
      id: item.item.id,
      sku: item.item.sku,
      name: item.item.name,
      unit_of_measure: item.item.unit_of_measure,
    },
  }
}

/**
 * All lot rows we need to render: warehouse pool + anything saved on the SO line + placeholders for
 * orphan lot_ids. Never drop allocations just because inventory API did not return the lot.
 */
function mergeLotsForLineDisplay(
  item: SalesOrderItem,
  available: Lot[],
  alloc: ItemAllocation | undefined,
): Lot[] {
  const byId = new Map<number, Lot>()
  for (const l of available) {
    byId.set(l.id, l)
  }
  if (item.allocated_lots?.length) {
    for (const al of item.allocated_lots) {
      if (!al.lot?.id) continue
      if (!byId.has(al.lot.id)) {
        byId.set(al.lot.id, al.lot)
      }
    }
  }
  if (alloc?.allocations?.length) {
    for (const a of alloc.allocations) {
      if (a.quantity <= 0 || byId.has(a.lot_id)) continue
      const fromSaved = item.allocated_lots?.find((x) => x.lot?.id === a.lot_id)
      if (fromSaved?.lot) {
        byId.set(a.lot_id, fromSaved.lot)
      } else {
        byId.set(a.lot_id, placeholderLot(item, a.lot_id))
      }
    }
  }
  return Array.from(byId.values())
}

function AllocateModal({ salesOrderId, onClose, onSuccess }: AllocateModalProps) {
  const [salesOrder, setSalesOrder] = useState<SalesOrder | null>(null)
  const [loading, setLoading] = useState(false)
  const [availableLots, setAvailableLots] = useState<Map<number, Lot[]>>(new Map())
  const [allocations, setAllocations] = useState<Map<number, ItemAllocation>>(new Map())
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [saving, setSaving] = useState(false)
  const [includeOnHoldLots, setIncludeOnHoldLots] = useState(false)
  /** Merge raw-inventory + FG lots (same SKU); required to pick vendor-labeled / pre-repack stock for distributed SKUs. */
  const [includePreRepackLots, setIncludePreRepackLots] = useState(false)
  /** Keys "productItemId:lotId" for lots that appear only on the raw-material path (pre-repack / vendor stock). */
  const [prerepackLotKeys, setPrerepackLotKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (salesOrderId) {
      loadSalesOrder(salesOrderId)
    }
  }, [salesOrderId])

  useEffect(() => {
    if (salesOrder && !salesOrder.drop_ship) {
      loadAvailableLots()
      initializeAllocations()
    }
  }, [salesOrder])

  useEffect(() => {
    if (salesOrder && !salesOrder.drop_ship) loadAvailableLots()
  }, [includeOnHoldLots, includePreRepackLots])

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
    const prerepackKeys = new Set<string>()

    for (const item of salesOrder.items) {
      try {
        // Do not pass Item.vendor — lots are keyed by PO vendor on the lot; Item.vendor often mismatches and hides all FG lots.
        const fgLots = await getLotsBySkuVendor(item.item.sku, undefined, 'finished_good')
        let combined: Lot[] = fgLots
        if (includePreRepackLots) {
          const rmLots = await getLotsBySkuVendor(item.item.sku, undefined, 'raw_material')
          const byId = new Map<number, Lot>()
          for (const l of fgLots) byId.set(l.id, l)
          for (const l of rmLots) {
            if (!byId.has(l.id)) {
              byId.set(l.id, l)
              prerepackKeys.add(`${item.item.id}:${l.id}`)
            }
          }
          combined = Array.from(byId.values())
        }

        const statusOk = (lot: Lot) =>
          lot.status === 'accepted' || (includeOnHoldLots && lot.status === 'on_hold')
        const matchesSoLine = (lot: Lot) =>
          lot.item.id === item.item.id || normalizeSku(lot.item.sku) === normalizeSku(item.item.sku)
        const available = combined.filter(
          (lot: Lot) =>
            lotAvailableForUse(lot) > 0 && matchesSoLine(lot) && statusOk(lot)
        )
        lotsMap.set(item.item.id, available)
      } catch (error) {
        console.error(`Failed to load lots for item ${item.item.sku}:`, error)
        lotsMap.set(item.item.id, [])
      }
    }

    setPrerepackLotKeys(prerepackKeys)
    setAvailableLots(lotsMap)
    // Do not strip allocations when lots are missing from the "available" pool — that pool is for
    // picking *additional* stock. Lines already allocated must stay in state so users can return
    // material to the warehouse slot even when inventory API returns no eligible rows.
  }

  const initializeAllocations = () => {
    if (!salesOrder) return

    const newAllocations = new Map<number, ItemAllocation>()
    
    for (const item of salesOrder.items) {
      const existingAllocations: Allocation[] = []
      
      if (item.allocated_lots) {
        for (const alloc of item.allocated_lots) {
          if (!alloc.lot?.id) continue
          existingAllocations.push({
            lot_id: alloc.lot.id,
            quantity: alloc.quantity_allocated
          })
        }
      }
      
      newAllocations.set(item.id, {
        item_id: item.item.id,
        is_distributed: item.item.item_type === 'distributed_item',
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

  /**
   * Clears one order line when the server has quantity_allocated but no SalesOrderLot rows (e.g. after
   * drop-ship-style allocate deleted lots, or inconsistent data). POST with empty allocations zeros the line.
   */
  const handleClearOrphanLineAllocation = async (item: SalesOrderItem) => {
    if (!salesOrder) return
    const qty = item.quantity_allocated ?? 0
    const displayUnit =
      unitDisplay === 'kg' && item.item.unit_of_measure === 'lbs'
        ? 'kg'
        : unitDisplay === 'lbs' && item.item.unit_of_measure === 'kg'
          ? 'lbs'
          : item.item.unit_of_measure
    const msg = [
      `Reset this line (${formatNumber(convertQuantity(qty, item.item.unit_of_measure))} ${displayUnit})?`,
      'It has no warehouse lots linked—only a line total. This sets the line to zero so you can allocate real lots.',
    ].join(' ')
    if (!window.confirm(msg)) return
    try {
      setSaving(true)
      await allocateSalesOrder(salesOrder.id, {
        items: [
          {
            item_id: item.item.id,
            is_distributed: item.item.item_type === 'distributed_item',
            allocations: [],
            raw_materials: [],
          },
        ],
        allow_prerepack_allocation: includePreRepackLots,
      })
      await loadSalesOrder(salesOrder.id)
      onSuccess()
    } catch (error: any) {
      console.error('Failed to clear line allocation:', error)
      alert(error.response?.data?.error || error.message || 'Request failed')
    } finally {
      setSaving(false)
    }
  }

  const handleDropShipConfirm = async () => {
    if (!salesOrder) return
    try {
      setSaving(true)
      await allocateSalesOrder(salesOrder.id, { items: [] })
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to confirm drop ship:', error)
      alert(error.response?.data?.error || error.response?.data?.detail || error.message || 'Request failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAllocations = async () => {
    if (!salesOrder) return

    // Check if any allocation uses an on-hold lot (ship under quarantine)
    let hasOnHoldAllocation = false
    for (const item of salesOrder.items) {
      const alloc = allocations.get(item.id)
      if (!alloc?.allocations?.length) continue
      const pool = availableLots.get(item.item.id) || []
      for (const a of alloc.allocations) {
        if (a.quantity <= 0) continue
        let lot = pool.find((l: Lot) => l.id === a.lot_id)
        if (!lot) lot = item.allocated_lots?.find((al) => al.lot?.id === a.lot_id)?.lot
        if (lot?.status === 'on_hold') {
          hasOnHoldAllocation = true
          break
        }
      }
      if (hasOnHoldAllocation) break
    }
    if (hasOnHoldAllocation && !window.confirm('One or more lots are on hold. Allocate under quarantine (ship under quarantine)?')) {
      return
    }

    try {
      setSaving(true)
      const itemsData: ItemAllocation[] = []

      for (const item of salesOrder.items) {
        const alloc = allocations.get(item.id)
        if (alloc) {
          itemsData.push(alloc)
        }
      }

      await allocateSalesOrder(salesOrder.id, {
        items: itemsData,
        allow_prerepack_allocation: includePreRepackLots,
      })
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

  if (salesOrder.drop_ship) {
    const linesOk = salesOrder.items.every(
      (it) => (it.quantity_allocated ?? 0) >= (it.quantity_ordered ?? 0)
    )
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="allocate-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Drop ship — {salesOrder.so_number}</h2>
            <button type="button" className="close-button" onClick={onClose}>×</button>
          </div>
          <div className="modal-content">
            <p className="drop-ship-explain">
              This order is <strong>drop ship</strong>: your vendor ships direct to the customer. No warehouse lots are used.
            </p>
            <p className="drop-ship-explain">
              Confirm to mark lines as ready to ship (for checkout) without pulling inventory.
            </p>
            <div className="modal-actions" style={{ marginTop: '1rem' }}>
              {linesOk ? (
                <button type="button" className="btn-save" onClick={onClose}>Close</button>
              ) : (
                <>
                  <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
                  <button
                    type="button"
                    className="btn-save"
                    onClick={() => void handleDropShipConfirm()}
                    disabled={saving}
                  >
                    {saving ? 'Saving…' : 'Confirm drop ship'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    )
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
            <p><strong>Expected Ship Date:</strong> {salesOrder.expected_ship_date ? formatAppDate(salesOrder.expected_ship_date) : 'Not set'}</p>
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
          <div className="include-on-hold-toggle">
            <label>
              <input
                type="checkbox"
                checked={includeOnHoldLots}
                onChange={(e) => setIncludeOnHoldLots(e.target.checked)}
              />
              Include lots on hold (ship under quarantine)
            </label>
            <label style={{ display: 'block', marginTop: '0.75rem' }}>
              <input
                type="checkbox"
                checked={includePreRepackLots}
                onChange={(e) => setIncludePreRepackLots(e.target.checked)}
              />
              Include raw / pre-repack lots (same SKU) for allocation
            </label>
            <p className="allocate-repack-hint" style={{ marginTop: '0.5rem', fontSize: '0.9rem', color: '#444' }}>
              {includePreRepackLots ? (
                <>
                  Listing <strong>finished-good (repack output)</strong> and <strong>raw / vendor</strong> lots, like both inventory tabs combined.
                  Use for vendor-labeled stock, pre-repack distributed lots, or receipt lots on <strong>gated finished goods</strong> (natural/synthetic colors, antioxidants) before a batch closes.
                  This checkbox is the only bypass—saving sends the override to the server.
                </>
              ) : (
                <>
                  <strong>Distributed (repack) SKUs:</strong> only lots from completed repack appear here.
                  <br />
                  <strong>Gated finished goods</strong> (colors / antioxidants): only lots from a <strong>closed repack or production batch</strong> appear—receipt stock stays on the Raw tab until then.
                </>
              )}
            </p>
          </div>

          <div className="allocation-items">
            {salesOrder.items.map(item => {
              const availableOnly = availableLots.get(item.item.id) || []
              const alloc = allocations.get(item.id)
              const merged = mergeLotsForLineDisplay(item, availableOnly, alloc)
              const allocatedOnLot = (lotId: number) =>
                alloc?.allocations.find((a) => a.lot_id === lotId)?.quantity ?? 0
              const onOrderLots = merged.filter((lot) => {
                const q = allocatedOnLot(lot.id)
                const saved =
                  item.allocated_lots?.find((al) => al.lot?.id === lot.id)?.quantity_allocated ?? 0
                return q > 0 || saved > 0
              })
              const orphanLineAllocation =
                onOrderLots.length === 0 && (item.quantity_allocated ?? 0) > 1e-6
              const onOrderIds = new Set(onOrderLots.map((l) => l.id))
              const warehouseLots = availableOnly.filter(
                (lot) =>
                  !onOrderIds.has(lot.id) &&
                  allocatedOnLot(lot.id) <= 0 &&
                  lotAvailableForUse(lot) > 0,
              )
              const totalAllocated = orphanLineAllocation
                ? (item.quantity_allocated ?? 0)
                : getTotalAllocated(item.id)
              const remaining = item.quantity_ordered - totalAllocated
              const unitDisplayText = unitDisplay === 'kg' && item.item.unit_of_measure === 'lbs' ? 'kg' : 
                                     unitDisplay === 'lbs' && item.item.unit_of_measure === 'kg' ? 'lbs' : 
                                     item.item.unit_of_measure
              const isFullyAlloc = totalAllocated + 1e-6 >= (item.quantity_ordered ?? 0)

              const renderLotRow = (lot: Lot, mode: 'onOrder' | 'warehouse') => {
                const lotAlloc = alloc?.allocations.find((a) => a.lot_id === lot.id)
                const allocatedQty = lotAlloc?.quantity || 0
                const availableQty = lotAvailableForUse(lot)
                const inAvailablePool = availableOnly.some((l) => l.id === lot.id)
                const maxAllocatable = Math.min(
                  allocatedQty + availableQty,
                  remaining + allocatedQty,
                )
                const savedAlloc = item.allocated_lots?.find((a) => a.lot?.id === lot.id)
                const coaUrl = savedAlloc?.coa_customer_pdf_url

                const isPrerepack =
                  includePreRepackLots && prerepackLotKeys.has(`${item.item.id}:${lot.id}`)
                return (
                  <tr
                    key={`${mode}-${lot.id}`}
                    className={[
                      lot.status === 'on_hold' ? 'lot-on-hold' : '',
                      isPrerepack ? 'lot-prerepack' : '',
                      mode === 'onOrder' ? 'lot-on-order-line' : '',
                      !inAvailablePool && allocatedQty > 0 ? 'lot-from-existing-allocation' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    <td>
                      {lot.lot_number}
                      {lot.status === 'on_hold' ? ' (on hold)' : ''}
                      {isPrerepack ? ' — pre-repack / vendor stock' : ''}
                      {mode === 'onOrder' && !inAvailablePool && allocatedQty > 0 ? (
                        <span
                          className="lot-merge-hint"
                          title="Not in the current warehouse pick list — clearing still returns this quantity to the lot / slot."
                        >
                          {' '}
                          (return to slot)
                        </span>
                      ) : null}
                    </td>
                    <td>
                      {mode === 'onOrder' ? (
                        <span title="Free stock in the warehouse for this lot; may be 0 while this order still holds an allocation.">
                          {formatNumber(convertQuantity(availableQty, lot.item.unit_of_measure))}{' '}
                          {unitDisplayText}
                        </span>
                      ) : (
                        <>
                          {formatNumber(convertQuantity(availableQty, lot.item.unit_of_measure))}{' '}
                          {unitDisplayText}
                        </>
                      )}
                    </td>
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
                      {coaUrl ? (
                        <a
                          href={coaUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="allocate-coa-link"
                          title="Customer COA for this allocation"
                        >
                          PDF
                        </a>
                      ) : (
                        <span className="allocate-coa-dash">—</span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn-allocate-full"
                        onClick={() => updateAllocation(item.id, lot.id, maxAllocatable)}
                        disabled={maxAllocatable <= 0}
                      >
                        {mode === 'onOrder' ? 'Use max' : 'Allocate all'}
                      </button>
                      {allocatedQty > 0 && (
                        <button
                          className="btn-clear"
                          onClick={() => updateAllocation(item.id, lot.id, 0)}
                        >
                          Clear (return to slot)
                        </button>
                      )}
                    </td>
                  </tr>
                )
              }

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
                    <div className="allocate-section allocate-section-on-order">
                      <h4>On this order</h4>
                      <p className="allocate-section-blurb">
                        Lower or clear a lot to put that quantity back on the lot in inventory.
                      </p>
                      {onOrderLots.length === 0 ? (
                        orphanLineAllocation ? (
                          <div className="allocate-orphan-line">
                            <p className="allocate-data-warning">
                              This line shows{' '}
                              {formatNumber(convertQuantity(item.quantity_allocated, item.item.unit_of_measure))}{' '}
                              {unitDisplayText} allocated, but <strong>no lots are linked</strong> (often after
                              drop-ship confirm or bad data). Reset the line, then pick lots in the next section.
                            </p>
                            <button
                              type="button"
                              className="btn-clear btn-clear-orphan"
                              disabled={saving}
                              onClick={() => void handleClearOrphanLineAllocation(item)}
                            >
                              {saving ? 'Saving…' : 'Reset line to zero'}
                            </button>
                          </div>
                        ) : (
                          <p className="no-lots">Nothing allocated on this line yet.</p>
                        )
                      ) : (
                        <table className="lots-table">
                          <thead>
                            <tr>
                              <th>Lot</th>
                              <th>Free in warehouse</th>
                              <th>On this order</th>
                              <th>COA</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>{onOrderLots.map((lot) => renderLotRow(lot, 'onOrder'))}</tbody>
                        </table>
                      )}
                    </div>

                    <div className="allocate-section allocate-section-warehouse">
                      <h4>From warehouse</h4>
                      <p className="allocate-section-blurb">
                        Add stock from inventory to cover what is still open on the order. To swap lots, clear the line
                        above first.
                      </p>
                      {warehouseLots.length === 0 ? (
                        <p className="no-lots muted">
                          No lots match this list for the SKU (or every matching lot is already on this line). Try
                          on-hold or pre-repack above.
                        </p>
                      ) : (
                        <table className="lots-table">
                          <thead>
                            <tr>
                              <th>Lot</th>
                              <th>Available</th>
                              <th>Allocate</th>
                              <th>COA</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>{warehouseLots.map((lot) => renderLotRow(lot, 'warehouse'))}</tbody>
                        </table>
                      )}
                    </div>
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
