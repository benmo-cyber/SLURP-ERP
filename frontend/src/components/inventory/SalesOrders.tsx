import { useState, useEffect } from 'react'
import { getSalesOrders } from '../../api/inventory'
import './SalesOrders.css'

function SalesOrders() {
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadOrders()
  }, [])

  const loadOrders = async () => {
    try {
      setLoading(true)
      const data = await getSalesOrders()
      setOrders(data)
    } catch (error) {
      console.error('Failed to load orders:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading sales orders...</div>
  }

  return (
    <div className="orders-container">
      <div className="orders-header">
        <h2>Sales Orders</h2>
        <button className="btn btn-primary">+ Add Sales Order</button>
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
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-state">
                  No sales orders found.
                </td>
              </tr>
            ) : (
              orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.so_number}</td>
                  <td>{order.customer_name}</td>
                  <td>
                    <span className={`badge badge-${order.status}`}>{order.status}</span>
                  </td>
                  <td>{new Date(order.order_date).toLocaleDateString()}</td>
                  <td>{order.expected_ship_date ? new Date(order.expected_ship_date).toLocaleDateString() : '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default SalesOrders

