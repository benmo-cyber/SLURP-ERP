import { useState, useEffect } from 'react'
import { getPurchaseOrders } from '../../api/inventory'
import './PurchaseOrders.css'

function PurchaseOrders() {
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadOrders()
  }, [])

  const loadOrders = async () => {
    try {
      setLoading(true)
      const data = await getPurchaseOrders()
      setOrders(data)
    } catch (error) {
      console.error('Failed to load orders:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading purchase orders...</div>
  }

  return (
    <div className="orders-container">
      <div className="orders-header">
        <h2>Purchase Orders</h2>
        <button className="btn btn-primary">+ Add Purchase Order</button>
      </div>

      <div className="orders-table-container">
        <table className="orders-table">
          <thead>
            <tr>
              <th>PO Number</th>
              <th>Type</th>
              <th>Vendor/Customer</th>
              <th>Status</th>
              <th>Order Date</th>
              <th>Expected Delivery</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  No purchase orders found.
                </td>
              </tr>
            ) : (
              orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.po_number}</td>
                  <td>{order.po_type}</td>
                  <td>{order.vendor_customer_name}</td>
                  <td>
                    <span className={`badge badge-${order.status}`}>{order.status}</span>
                  </td>
                  <td>{new Date(order.order_date).toLocaleDateString()}</td>
                  <td>{order.expected_delivery_date ? new Date(order.expected_delivery_date).toLocaleDateString() : '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default PurchaseOrders

