import { useState, useEffect, useMemo } from 'react'
import { useGodMode } from '../../context/GodModeContext'
import {
  getSalesOrders,
  deleteSalesOrder,
  updateSalesOrder,
  patchSalesOrder,
  issueSalesOrder,
  openPackingList,
  openPackingListForShipment,
  openPickList,
} from '../../api/salesOrders'
import { formatNumber } from '../../utils/formatNumber'
import { formatAppDate } from '../../utils/appDateFormat'
import AllocateModal from './AllocateModal'
import './SalesOrdersList.css'

interface SalesOrder {
  id: number
  so_number: string
  customer_name: string
  customer_reference_number?: string
  customer_address?: string
  customer_city?: string
  customer_state?: string
  customer_zip?: string
  status: string
  order_date: string
  expected_ship_date?: string
  actual_ship_date?: string
  grand_total?: number
  drop_ship?: boolean
  items?: Array<{
    id: number
    item: {
      sku: string
      name: string
      unit_of_measure?: string
    }
    quantity_ordered: number
    quantity_allocated: number
    unit_price: number
    allocated_lots?: Array<{
      id: number
      quantity_allocated: number
      coa_customer_pdf_url?: string | null
      lot?: {
        id: number
        lot_number?: string | null
        vendor_lot_number?: string | null
      }
    }>
  }>
  shipments?: Array<{
    id: number
    ship_date: string
    expected_ship_date?: string | null
    tracking_number?: string
  }>
}

interface SalesOrdersListProps {
  refreshKey?: number
  onSelectOrder?: (order: SalesOrder) => void
  onEditOrder?: (order: SalesOrder) => void
}

type CustomerCoaRow = {
  key: number
  sku: string
  lotLabel: string
  qty: number
  uom: string
  url: string | null | undefined
}

function customerCoaRowsForOrder(order: SalesOrder): CustomerCoaRow[] {
  const rows: CustomerCoaRow[] = []
  for (const item of order.items ?? []) {
    const uom = (item.item?.unit_of_measure || 'lbs').toLowerCase()
    for (const al of item.allocated_lots ?? []) {
      const lotLabel = ((al.lot?.lot_number || al.lot?.vendor_lot_number || '—') as string).trim()
      rows.push({
        key: al.id,
        sku: item.item?.sku || '—',
        lotLabel,
        qty: al.quantity_allocated,
        uom,
        url: al.coa_customer_pdf_url,
      })
    }
  }
  return rows
}

function customerCoaOpenTitle(sku: string, lotLabel: string) {
  return `Open customer COA PDF for this sales order (${sku} · lot ${lotLabel})`
}

function customerCoaPendingTitle(sku: string, lotLabel: string) {
  return `Customer COA not ready for ${sku} · ${lotLabel}. Appears when the customer copy is generated for this allocation.`
}

function SalesOrdersList({ refreshKey = 0, onSelectOrder, onEditOrder }: SalesOrdersListProps) {
  const [orders, setOrders] = useState<SalesOrder[]>([])
  const [completedOrders, setCompletedOrders] = useState<SalesOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [editingShipDateId, setEditingShipDateId] = useState<number | null>(null)
  const [editingShipDate, setEditingShipDate] = useState<string>('')
  const [issuingId, setIssuingId] = useState<number | null>(null)
  const [allocatingSOId, setAllocatingSOId] = useState<number | null>(null)
  const [issueModalOrder, setIssueModalOrder] = useState<SalesOrder | null>(null)
  const [issueDateValue, setIssueDateValue] = useState('')
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
  type SOSortKey = 'so_number' | 'customer_name' | 'status' | 'order_date' | 'expected_ship_date' | 'grand_total' | null
  const [sort, setSort] = useState<{ key: SOSortKey; dir: 'asc' | 'desc' }>({ key: 'order_date', dir: 'desc' })

  useEffect(() => {
    loadOrders()
  }, [refreshKey])

  const sortOrderList = (list: SalesOrder[]) => {
    if (!sort.key) return list
    return [...list].sort((a, b) => {
      let cmp = 0
      switch (sort.key) {
        case 'so_number': cmp = (a.so_number || '').localeCompare(b.so_number || ''); break
        case 'customer_name': cmp = (a.customer_name || '').localeCompare(b.customer_name || ''); break
        case 'status': cmp = (a.status || '').localeCompare(b.status || ''); break
        case 'order_date': cmp = new Date(a.order_date).getTime() - new Date(b.order_date).getTime(); break
        case 'expected_ship_date': cmp = new Date(a.expected_ship_date || 0).getTime() - new Date(b.expected_ship_date || 0).getTime(); break
        case 'grand_total': cmp = (a.grand_total ?? 0) - (b.grand_total ?? 0); break
        default: return 0
      }
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }
  const handleSort = (key: NonNullable<SOSortKey>) => {
    setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  const loadOrders = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getSalesOrders()
      // Handle paginated response
      const ordersList = Array.isArray(data) ? data : (data.results || [])
      // Separate active and completed orders (sort applied in render)
      const active = ordersList.filter((so: SalesOrder) => so.status !== 'completed')
      const completed = ordersList.filter((so: SalesOrder) => so.status === 'completed')
      setOrders(active)
      setCompletedOrders(completed)
    } catch (err: any) {
      console.error('Failed to load sales orders:', err)
      setError(err.response?.data?.detail || 'Failed to load sales orders')
    } finally {
      setLoading(false)
    }
  }

  const formatStatusLabel = (status: string) => (status || '').replace(/_/g, ' ')

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'draft':
        return 'badge-draft'
      case 'allocated':
        return 'badge-allocated'
      case 'issued':
      case 'ready_for_shipment':
        return 'badge-issued'
      case 'shipped':
      case 'completed':
        return 'badge-shipped'
      case 'cancelled':
        return 'badge-cancelled'
      default:
        return 'badge-default'
    }
  }

  const handleRowClick = (order: SalesOrder) => {
    if (onSelectOrder) {
      onSelectOrder(order)
    }
  }

  const handleEdit = (e: React.MouseEvent, order: SalesOrder) => {
    e.stopPropagation()
    if (onEditOrder) {
      onEditOrder(order)
    }
  }

  const handleShipDateEdit = (order: SalesOrder) => {
    setEditingShipDateId(order.id)
    setEditingShipDate(order.expected_ship_date ? order.expected_ship_date.split('T')[0] : '')
  }

  const handleShipDateSave = async (orderId: number) => {
    try {
      await patchSalesOrder(orderId, { expected_ship_date: editingShipDate || null })
      setEditingShipDateId(null)
      await loadOrders()
    } catch (err: any) {
      console.error('Failed to update ship date:', err)
      alert(`Failed to update ship date: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleShipDateCancel = () => {
    setEditingShipDateId(null)
    setEditingShipDate('')
  }

  const submitIssueFromModal = async () => {
    if (!issueModalOrder) return
    try {
      setIssuingId(issueModalOrder.id)
      await issueSalesOrder(issueModalOrder.id, { issue_date: issueDateValue })
      setIssueModalOrder(null)
      await loadOrders()
    } catch (err: any) {
      console.error('Failed to issue sales order:', err)
      alert(`Failed to issue sales order: ${err.response?.data?.error || err.response?.data?.detail || err.message}`)
    } finally {
      setIssuingId(null)
    }
  }

  const handleIssue = async (e: React.MouseEvent, order: SalesOrder) => {
    e.stopPropagation()
    
    if (order.status !== 'draft') {
      alert(`Cannot issue a ${order.status} sales order. Only draft orders can be issued.`)
      return
    }

    if (godModeOn && canUseGodMode) {
      setIssueModalOrder(order)
      setIssueDateValue(order.order_date ? order.order_date.slice(0, 10) : todayYmd)
      return
    }

    if (!confirm(`Are you sure you want to issue sales order ${order.so_number}?`)) {
      return
    }

    try {
      setIssuingId(order.id)
      await issueSalesOrder(order.id)
      await loadOrders()
    } catch (err: any) {
      console.error('Failed to issue sales order:', err)
      alert(`Failed to issue sales order: ${err.response?.data?.error || err.response?.data?.detail || err.message}`)
    } finally {
      setIssuingId(null)
    }
  }

  const handleAllocate = (e: React.MouseEvent, order: SalesOrder) => {
    e.stopPropagation()
    setAllocatingSOId(order.id)
  }

  const handleAllocateSuccess = () => {
    setAllocatingSOId(null)
    loadOrders()
  }

  const isFullyAllocated = (order: SalesOrder): boolean => {
    if (!order.items || order.items.length === 0) return false
    return order.items.every(item => item.quantity_allocated >= item.quantity_ordered)
  }

  /** Packing list PDF uses carrier, tracking, pieces, dimensions & weights from checkout — enable only after at least one shipment. */
  const canOpenOrderPackingList = (order: SalesOrder): boolean =>
    Boolean(order.shipments && order.shipments.length > 0)

  const packingListDisabledTitle =
    'Complete checkout first. Carrier, tracking, pieces, per-piece dimensions and weights are saved to the packing list. Then open Pack list or a Release link.'

  const canOpenPickList = (order: SalesOrder): boolean =>
    Boolean(order.items?.some((it) => (it.quantity_allocated ?? 0) > 0))

  const pickListDisabledTitle =
    'Allocate inventory first. The pick list shows each SKU, Wildwood lot number, and quantity to pull from the warehouse.'

  const handleDelete = async (e: React.MouseEvent, order: SalesOrder) => {
    e.stopPropagation()
    
    // Prevent deletion of shipped or cancelled orders
    if (order.status === 'shipped' || order.status === 'cancelled') {
      alert(`Cannot delete a ${order.status} sales order.`)
      return
    }

    // Check if order has allocations
    const hasAllocations = order.items?.some(item => item.quantity_allocated > 0)
    if (hasAllocations) {
      if (!confirm(`This sales order has allocated inventory. Deleting it will remove all allocations. Are you sure you want to delete ${order.so_number}?`)) {
        return
      }
    } else {
      if (!confirm(`Are you sure you want to delete sales order ${order.so_number}?`)) {
        return
      }
    }

    try {
      setDeletingId(order.id)
      await deleteSalesOrder(order.id)
      // Reload orders after deletion
      await loadOrders()
    } catch (err: any) {
      console.error('Failed to delete sales order:', err)
      alert(`Failed to delete sales order: ${err.response?.data?.detail || err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  const issueModal = issueModalOrder ? (
      <div
        className="modal-overlay"
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={() => setIssueModalOrder(null)}
      >
        <div
          style={{ background: 'white', padding: '1.5rem', borderRadius: 8, maxWidth: 420 }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 style={{ marginTop: 0 }}>Issue sales order</h3>
          <p style={{ marginBottom: '0.75rem' }}>Choose the order / issue date (shown on documents).</p>
          <div className="form-group">
            <label htmlFor="so-issue-date">Order date</label>
            <input
              id="so-issue-date"
              type="date"
              value={issueDateValue}
              onChange={(e) => setIssueDateValue(e.target.value)}
              max={maxDateForEntry}
              min={minDateForEntry}
            />
          </div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-primary" onClick={() => void submitIssueFromModal()}>
              Issue SO
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setIssueModalOrder(null)}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    ) : null

  if (loading) {
    return (
      <>
        {issueModal}
        <div className="sales-orders-list">
          <div className="loading">Loading sales orders...</div>
        </div>
      </>
    )
  }

  if (error) {
    return (
      <>
        {issueModal}
        <div className="sales-orders-list">
          <div className="error-message">{error}</div>
          <button onClick={loadOrders} className="btn btn-secondary">Retry</button>
        </div>
      </>
    )
  }

  return (
    <>
      {issueModal}
    <div className="sales-orders-list">
      <div className="orders-header">
        <h2>Sales Orders</h2>
        <div className="orders-stats">
          <span>Total Orders: {orders.length}</span>
        </div>
      </div>

      <div className="orders-table-container table-wrapper">
        <table className="orders-table">
          <thead>
            <tr>
              <th className="sortable sortable-header" onClick={() => handleSort('so_number')}>SO # {sort.key === 'so_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('customer_name')}>Customer {sort.key === 'customer_name' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('status')}>Status {sort.key === 'status' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('order_date')}>Order date {sort.key === 'order_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('expected_ship_date')}>Exp. ship {sort.key === 'expected_ship_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>Line items</th>
              <th className="sortable sortable-header" onClick={() => handleSort('grand_total')}>Total {sort.key === 'grand_total' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="so-shipping-th">Shipping</th>
              <th className="so-actions-th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr>
                <td colSpan={9} className="empty-state">
                  No sales orders found.
                </td>
              </tr>
            ) : (
              sortOrderList(orders).map((order) => (
                <tr 
                  key={order.id} 
                  className={onSelectOrder ? 'clickable-row' : ''}
                  onClick={() => handleRowClick(order)}
                >
                  <td className="so-number">
                    <div className="so-number-cell">
                      <div className="so-number-main">{order.so_number}</div>
                      {order.customer_reference_number && (
                        <div className="customer-po-number">PO: {order.customer_reference_number}</div>
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="customer-info">
                      <div className="customer-name">{order.customer_name}</div>
                      {order.customer_city && (
                        <div className="customer-location">
                          {order.customer_city}{order.customer_state ? `, ${order.customer_state}` : ''}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="so-status-td">
                    <span className={`badge ${getStatusBadgeClass(order.status)}`}>
                      {formatStatusLabel(order.status)}
                    </span>
                    {order.drop_ship && (
                      <span className="badge badge-drop-ship" title="Drop ship">DS</span>
                    )}
                  </td>
                  <td>{formatAppDate(order.order_date)}</td>
                  <td>
                    {editingShipDateId === order.id ? (
                      <div className="ship-date-edit">
                        <input
                          type="date"
                          value={editingShipDate}
                          onChange={(e) => setEditingShipDate(e.target.value)}
                          className="date-input"
                          autoFocus
                        />
                        <button
                          onClick={() => handleShipDateSave(order.id)}
                          className="btn-save-small"
                          title="Save"
                        >
                          ✓
                        </button>
                        <button
                          onClick={handleShipDateCancel}
                          className="btn-cancel-small"
                          title="Cancel"
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <span 
                        className="editable-ship-date"
                        onClick={() => handleShipDateEdit(order)}
                        title="Click to edit"
                      >
                        {order.expected_ship_date 
                          ? formatAppDate(order.expected_ship_date) 
                          : '-'}
                      </span>
                    )}
                  </td>
                  <td className="so-items-td">
                    {order.items && order.items.length > 0 ? (
                      <div className="so-items-list">
                        {order.items.map((item, idx) => {
                          const alloc = item.quantity_allocated ?? 0
                          const ordered = item.quantity_ordered ?? 0
                          const fully = alloc >= ordered && ordered > 0
                          const uom = (item.item?.unit_of_measure || 'lbs').toLowerCase()
                          const lotLabel = (lot: { lot_number?: string | null; vendor_lot_number?: string | null } | undefined) =>
                            ((lot?.lot_number || lot?.vendor_lot_number || '—') as string).trim()
                          return (
                            <div key={item.id ?? idx} className="so-item-block">
                              <div className="so-item-row">
                                <span className="so-item-sku">{item.item?.sku || '—'}</span>
                                <span className="so-item-name" title={item.item?.name || ''}>
                                  {item.item?.name || '—'}
                                </span>
                                <span className="so-item-qty">
                                  {formatNumber(ordered)}
                                  <span className="so-item-uom">{uom}</span>
                                </span>
                              </div>
                              {alloc > 0 && (
                                <div className={`so-item-alloc ${fully ? 'so-item-alloc--full' : ''}`}>
                                  {formatNumber(alloc)} {uom} allocated
                                  {fully ? ' · complete' : ''}
                                </div>
                              )}
                              {item.allocated_lots &&
                                item.allocated_lots.length > 0 &&
                                (alloc > 0 || order.status === 'completed') && (
                                <ul className="so-alloc-lots">
                                  {item.allocated_lots.map((al) => (
                                    <li key={al.id} className="so-alloc-lot-row">
                                      <span className="so-alloc-lot-text">
                                        {lotLabel(al.lot)} · {formatNumber(al.quantity_allocated)} {uom}
                                        {order.status === 'completed' && (al.quantity_allocated ?? 0) <= 0
                                          ? ' · shipped'
                                          : ''}
                                      </span>
                                      {al.coa_customer_pdf_url ? (
                                        <a
                                          href={al.coa_customer_pdf_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="so-coa-link"
                                          onClick={(e) => e.stopPropagation()}
                                          title={customerCoaOpenTitle(item.item?.sku || '—', lotLabel(al.lot))}
                                        >
                                          COA
                                        </a>
                                      ) : (
                                        <span
                                          className="so-coa-missing"
                                          title={customerCoaPendingTitle(item.item?.sku || '—', lotLabel(al.lot))}
                                        >
                                          COA
                                        </span>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <span className="so-items-empty">—</span>
                    )}
                  </td>
                  <td className="total-column">
                    {order.grand_total !== undefined && order.grand_total !== null
                      ? `$${formatNumber(order.grand_total, 2)}`
                      : '-'}
                  </td>
                  <td className="so-shipping-td" onClick={(e) => e.stopPropagation()}>
                    <div className="so-shipping-cell">
                      <div className="so-shipping-buttons">
                        <button
                          type="button"
                          className="so-act-btn so-act-btn--pick"
                          disabled={!canOpenPickList(order)}
                          onClick={() => {
                            if (!canOpenPickList(order)) return
                            openPickList(order.id)
                          }}
                          title={canOpenPickList(order) ? 'Pick list: lots and quantities to pull from the warehouse' : pickListDisabledTitle}
                        >
                          Pick list
                        </button>
                        <button
                          type="button"
                          className="so-act-btn so-act-btn--ship"
                          disabled={!canOpenOrderPackingList(order)}
                          onClick={() => {
                            if (!canOpenOrderPackingList(order)) return
                            void openPackingList(order.id)
                          }}
                          title={
                            canOpenOrderPackingList(order)
                              ? 'Packing list (full order summary)'
                              : packingListDisabledTitle
                          }
                        >
                          Pack list
                        </button>
                      </div>
                      {order.shipments && order.shipments.length > 0 && (
                        <div className="so-pl-releases">
                          {order.shipments.map((s, idx) => (
                            <button
                              key={s.id}
                              type="button"
                              className="so-pl-release-link"
                              onClick={() => openPackingListForShipment(s.id)}
                              title={`Packing list for shipment ${idx + 1}${s.ship_date ? ` (${String(s.ship_date).slice(0, 10)})` : ''}`}
                            >
                              Release {idx + 1}
                            </button>
                          ))}
                        </div>
                      )}
                      {(() => {
                        const coaRows = customerCoaRowsForOrder(order)
                        if (coaRows.length === 0) return null
                        return (
                          <div className="so-order-coas">
                            {coaRows.map((row) =>
                              row.url ? (
                                <a
                                  key={row.key}
                                  href={row.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="so-act-btn so-act-btn--coa"
                                  onClick={(e) => e.stopPropagation()}
                                  title={customerCoaOpenTitle(row.sku, row.lotLabel)}
                                >
                                  COA
                                </a>
                              ) : (
                                <span
                                  key={row.key}
                                  className="so-act-btn so-act-btn--coa so-act-btn--coa-missing"
                                  title={customerCoaPendingTitle(row.sku, row.lotLabel)}
                                >
                                  COA
                                </span>
                              ),
                            )}
                          </div>
                        )
                      })()}
                    </div>
                  </td>
                  <td className="actions-column" onClick={(e) => e.stopPropagation()}>
                    <div className="so-action-buttons">
                      {order.status === 'draft' && (
                        <>
                          <button
                            type="button"
                            className="so-act-btn so-act-btn--primary"
                            onClick={(e) => handleAllocate(e, order)}
                            title={isFullyAllocated(order) ? 'Re-allocate inventory' : 'Allocate inventory'}
                          >
                            {isFullyAllocated(order) ? 'Re-alloc' : 'Allocate'}
                          </button>
                          <button
                            type="button"
                            className="so-act-btn so-act-btn--issue"
                            onClick={(e) => handleIssue(e, order)}
                            disabled={issuingId === order.id}
                            title="Issue sales order"
                          >
                            {issuingId === order.id ? '…' : 'Issue'}
                          </button>
                        </>
                      )}
                      {(order.status === 'allocated' || order.status === 'issued' || order.status === 'ready_for_shipment') && (
                        <button
                          type="button"
                          className="so-act-btn so-act-btn--primary"
                          onClick={(e) => handleAllocate(e, order)}
                          title={isFullyAllocated(order) ? 'Re-allocate inventory' : 'Allocate inventory'}
                        >
                          {isFullyAllocated(order) ? 'Re-alloc' : 'Allocate'}
                        </button>
                      )}
                      {onEditOrder && (order.status === 'draft' || order.status === 'allocated' || order.status === 'issued') && (
                        <button
                          type="button"
                          className="so-act-btn so-act-btn--muted"
                          onClick={(e) => handleEdit(e, order)}
                          title="Edit sales order"
                        >
                          Edit
                        </button>
                      )}
                      {(order.status === 'draft' || order.status === 'allocated') && (
                        <button
                          type="button"
                          className="so-act-btn so-act-btn--danger"
                          onClick={(e) => handleDelete(e, order)}
                          disabled={deletingId === order.id}
                          title="Delete sales order"
                        >
                          {deletingId === order.id ? '…' : 'Delete'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {allocatingSOId && (
        <AllocateModal
          salesOrderId={allocatingSOId}
          onClose={() => setAllocatingSOId(null)}
          onSuccess={handleAllocateSuccess}
        />
      )}

      {completedOrders.length > 0 && (
        <div className="completed-orders-section">
          <div className="orders-header">
            <h2>Completed Sales Orders</h2>
            <div className="orders-stats">
              <span>Total Completed: {completedOrders.length}</span>
            </div>
          </div>

          <div className="orders-table-container table-wrapper">
            <table className="orders-table">
              <thead>
                <tr>
                  <th className="sortable sortable-header" onClick={() => handleSort('so_number')}>SO # {sort.key === 'so_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
                  <th className="sortable sortable-header" onClick={() => handleSort('customer_name')}>Customer {sort.key === 'customer_name' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
                  <th className="sortable sortable-header" onClick={() => handleSort('order_date')}>Order date {sort.key === 'order_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
                  <th>Ship dates</th>
                  <th>Line items</th>
                  <th className="so-shipping-th">Shipping</th>
                  <th className="sortable sortable-header" onClick={() => handleSort('grand_total')}>Total {sort.key === 'grand_total' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
                </tr>
              </thead>
              <tbody>
                {sortOrderList(completedOrders).map((order) => (
                  <tr key={order.id}>
                    <td className="so-number">
                      <div className="so-number-cell">
                        <div className="so-number-main">{order.so_number}</div>
                        {order.customer_reference_number && (
                          <div className="customer-po-number">PO: {order.customer_reference_number}</div>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="customer-info">
                        <div className="customer-name">{order.customer_name}</div>
                        {order.customer_city && (
                          <div className="customer-location">
                            {order.customer_city}{order.customer_state ? `, ${order.customer_state}` : ''}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>{formatAppDate(order.order_date)}</td>
                    <td>
                      {order.shipments && order.shipments.length > 0 ? (
                        <div className="ship-dates-list">
                          {order.shipments.map((shipment, idx) => (
                            <div key={shipment.id} className="ship-date-item">
                              {formatAppDate(shipment.ship_date)}
                              {shipment.tracking_number && (
                                <span className="tracking-number"> ({shipment.tracking_number})</span>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        order.actual_ship_date ? formatAppDate(order.actual_ship_date) : '-'
                      )}
                    </td>
                    <td className="so-items-td">
                      {order.items && order.items.length > 0 ? (
                        <div className="so-items-list">
                          {order.items.map((item, idx) => {
                            const uom = (item.item?.unit_of_measure || 'lbs').toLowerCase()
                            const alloc = item.quantity_allocated ?? 0
                            const lotLabel = (lot: { lot_number?: string | null; vendor_lot_number?: string | null } | undefined) =>
                              ((lot?.lot_number || lot?.vendor_lot_number || '—') as string).trim()
                            return (
                              <div key={item.id ?? idx} className="so-item-block so-item-block--compact">
                                <div className="so-item-row">
                                  <span className="so-item-sku">{item.item?.sku || '—'}</span>
                                  <span className="so-item-name" title={item.item?.name || ''}>
                                    {item.item?.name || '—'}
                                  </span>
                                  <span className="so-item-qty">
                                    {formatNumber(item.quantity_ordered)}
                                    <span className="so-item-uom">{uom}</span>
                                  </span>
                                </div>
                                {item.allocated_lots &&
                                  item.allocated_lots.length > 0 &&
                                  (alloc > 0 || order.status === 'completed') && (
                                  <ul className="so-alloc-lots">
                                    {item.allocated_lots.map((al) => (
                                      <li key={al.id} className="so-alloc-lot-row">
                                        <span className="so-alloc-lot-text">
                                          {lotLabel(al.lot)} · {formatNumber(al.quantity_allocated)} {uom}
                                          {order.status === 'completed' && (al.quantity_allocated ?? 0) <= 0
                                            ? ' · shipped'
                                            : ''}
                                        </span>
                                        {al.coa_customer_pdf_url ? (
                                          <a
                                            href={al.coa_customer_pdf_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="so-coa-link"
                                            onClick={(e) => e.stopPropagation()}
                                            title={customerCoaOpenTitle(item.item?.sku || '—', lotLabel(al.lot))}
                                          >
                                            COA
                                          </a>
                                        ) : (
                                          <span
                                            className="so-coa-missing"
                                            title={customerCoaPendingTitle(item.item?.sku || '—', lotLabel(al.lot))}
                                          >
                                            COA
                                          </span>
                                        )}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      ) : (
                        <span className="so-items-empty">—</span>
                      )}
                    </td>
                    <td className="so-shipping-td" onClick={(e) => e.stopPropagation()}>
                      <div className="so-shipping-cell">
                        <div className="so-shipping-buttons">
                          <button
                            type="button"
                            className="so-act-btn so-act-btn--pick"
                            disabled={!canOpenPickList(order)}
                            onClick={() => {
                              if (!canOpenPickList(order)) return
                              openPickList(order.id)
                            }}
                            title={canOpenPickList(order) ? 'Pick list: lots and quantities' : pickListDisabledTitle}
                          >
                            Pick list
                          </button>
                          <button
                            type="button"
                            className="so-act-btn so-act-btn--ship"
                            disabled={!canOpenOrderPackingList(order)}
                            onClick={() => {
                              if (!canOpenOrderPackingList(order)) return
                              void openPackingList(order.id)
                            }}
                            title={
                              canOpenOrderPackingList(order)
                                ? 'Packing list (full order summary)'
                                : packingListDisabledTitle
                            }
                          >
                            Pack list
                          </button>
                        </div>
                        {order.shipments && order.shipments.length > 0 && (
                          <div className="so-pl-releases">
                            {order.shipments.map((s, idx) => (
                              <button
                                key={s.id}
                                type="button"
                                className="so-pl-release-link"
                                onClick={() => openPackingListForShipment(s.id)}
                                title={`Packing list for shipment ${idx + 1}`}
                              >
                                Release {idx + 1}
                              </button>
                            ))}
                          </div>
                        )}
                        {(() => {
                          const coaRows = customerCoaRowsForOrder(order)
                          if (coaRows.length === 0) return null
                          return (
                            <div className="so-order-coas">
                              {coaRows.map((row) =>
                                row.url ? (
                                  <a
                                    key={row.key}
                                    href={row.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="so-act-btn so-act-btn--coa"
                                    onClick={(e) => e.stopPropagation()}
                                    title={customerCoaOpenTitle(row.sku, row.lotLabel)}
                                  >
                                    COA
                                  </a>
                                ) : (
                                  <span
                                    key={row.key}
                                    className="so-act-btn so-act-btn--coa so-act-btn--coa-missing"
                                    title={customerCoaPendingTitle(row.sku, row.lotLabel)}
                                  >
                                    COA
                                  </span>
                                ),
                              )}
                            </div>
                          )
                        })()}
                      </div>
                    </td>
                    <td className="total-column">
                      {order.grand_total !== undefined && order.grand_total !== null
                        ? `$${formatNumber(order.grand_total, 2)}`
                        : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
    </>
  )
}

export default SalesOrdersList
