import { useState, useEffect } from 'react'
import { getSalesOrders, deleteSalesOrder, updateSalesOrder, issueSalesOrder } from '../../api/salesOrders'
import { formatNumber } from '../../utils/formatNumber'
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
  items?: Array<{
    id: number
    item: {
      sku: string
      name: string
    }
    quantity_ordered: number
    quantity_allocated: number
    unit_price: number
  }>
}

interface SalesOrdersListProps {
  refreshKey?: number
  onSelectOrder?: (order: SalesOrder) => void
  onEditOrder?: (order: SalesOrder) => void
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

  useEffect(() => {
    loadOrders()
  }, [refreshKey])

  const loadOrders = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getSalesOrders()
      // Handle paginated response
      const ordersList = Array.isArray(data) ? data : (data.results || [])
      // Sort by order date descending (newest first)
      ordersList.sort((a: SalesOrder, b: SalesOrder) => 
        new Date(b.order_date).getTime() - new Date(a.order_date).getTime()
      )
      // Separate active and completed orders
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

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'draft':
        return 'badge-draft'
      case 'allocated':
        return 'badge-allocated'
      case 'shipped':
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
      await updateSalesOrder(orderId, { expected_ship_date: editingShipDate || null })
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

  const handleIssue = async (e: React.MouseEvent, order: SalesOrder) => {
    e.stopPropagation()
    
    if (order.status !== 'draft') {
      alert(`Cannot issue a ${order.status} sales order. Only draft orders can be issued.`)
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

  if (loading) {
    return (
      <div className="sales-orders-list">
        <div className="loading">Loading sales orders...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="sales-orders-list">
        <div className="error-message">{error}</div>
        <button onClick={loadOrders} className="btn btn-secondary">Retry</button>
      </div>
    )
  }

  return (
    <div className="sales-orders-list">
      <div className="orders-header">
        <h2>Sales Orders</h2>
        <div className="orders-stats">
          <span>Total Orders: {orders.length}</span>
        </div>
      </div>

      <div className="orders-table-container">
        <table className="orders-table">
          <thead>
            <tr>
              <th>SO Number</th>
              <th>Customer</th>
              <th>Status</th>
              <th>Order Date</th>
              <th>Expected Ship Date</th>
              <th>Items</th>
              <th>Total</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  No sales orders found.
                </td>
              </tr>
            ) : (
              orders.map((order) => (
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
                  <td>
                    <span className={`badge ${getStatusBadgeClass(order.status)}`}>
                      {order.status}
                    </span>
                  </td>
                  <td>{new Date(order.order_date).toLocaleDateString()}</td>
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
                          ? new Date(order.expected_ship_date).toLocaleDateString() 
                          : '-'}
                      </span>
                    )}
                  </td>
                  <td>
                    {order.items && order.items.length > 0 ? (
                      <div className="items-list">
                        {order.items.map((item, idx) => (
                          <div key={idx} className="item-line">
                            <span className="item-sku">{item.item.sku}</span>
                            <span className="item-quantity">{formatNumber(item.quantity_ordered)}</span>
                            {item.quantity_allocated > 0 && (
                              <span className="allocated-badge">
                                ({formatNumber(item.quantity_allocated)} allocated)
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="total-column">
                    {order.items && order.items.length > 0 ? (
                      <div className="totals-list">
                        {order.items.map((item, idx) => (
                          <div key={idx} className="total-line">
                            {formatNumber(item.quantity_ordered)} × ${formatNumber(item.unit_price || 0, 2)} = ${formatNumber((item.quantity_ordered || 0) * (item.unit_price || 0), 2)}
                          </div>
                        ))}
                        {order.grand_total !== undefined && order.grand_total !== null && (
                          <div className="grand-total">
                            Total: ${formatNumber(order.grand_total, 2)}
                          </div>
                        )}
                      </div>
                    ) : (
                      order.grand_total !== undefined && order.grand_total !== null
                        ? `$${formatNumber(order.grand_total, 2)}`
                        : '-'
                    )}
                  </td>
                  <td className="actions-column">
                    <div className="action-buttons">
                      {order.status === 'draft' && (
                        <button
                          className="btn-icon btn-issue"
                          onClick={(e) => handleIssue(e, order)}
                          disabled={issuingId === order.id}
                          title="Issue"
                        >
                          {issuingId === order.id ? '⏳' : '📋'}
                        </button>
                      )}
                      {order.status === 'issued' && (
                        <button
                          className="btn-action btn-allocate"
                          onClick={(e) => handleAllocate(e, order)}
                          title={isFullyAllocated(order) ? 'Re-allocate' : 'Allocate'}
                        >
                          {isFullyAllocated(order) ? 'Re-allocate' : 'Allocate'}
                        </button>
                      )}
                      {onEditOrder && (order.status === 'draft' || order.status === 'allocated' || order.status === 'issued') && (
                        <button
                          className="btn-icon btn-edit"
                          onClick={(e) => handleEdit(e, order)}
                          title="Edit"
                        >
                          ✏️
                        </button>
                      )}
                      {(order.status === 'draft' || order.status === 'allocated') && (
                        <button
                          className="btn-icon btn-delete"
                          onClick={(e) => handleDelete(e, order)}
                          disabled={deletingId === order.id}
                          title="Delete"
                        >
                          {deletingId === order.id ? '⏳' : '🗑️'}
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

          <div className="orders-table-container">
            <table className="orders-table">
              <thead>
                <tr>
                  <th>SO Number</th>
                  <th>Customer</th>
                  <th>Order Date</th>
                  <th>Ship Dates</th>
                  <th>Items</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {completedOrders.map((order) => (
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
                    <td>{new Date(order.order_date).toLocaleDateString()}</td>
                    <td>
                      {order.shipments && order.shipments.length > 0 ? (
                        <div className="ship-dates-list">
                          {order.shipments.map((shipment, idx) => (
                            <div key={shipment.id} className="ship-date-item">
                              {new Date(shipment.ship_date).toLocaleDateString()}
                              {shipment.tracking_number && (
                                <span className="tracking-number"> ({shipment.tracking_number})</span>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        order.actual_ship_date ? new Date(order.actual_ship_date).toLocaleDateString() : '-'
                      )}
                    </td>
                    <td>
                      {order.items && order.items.length > 0 ? (
                        <div className="items-list">
                          {order.items.map((item, idx) => (
                            <div key={idx} className="item-line">
                              <span className="item-sku">{item.item.sku}</span>
                              <span className="item-quantity">{formatNumber(item.quantity_ordered)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        '-'
                      )}
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
  )
}

export default SalesOrdersList
