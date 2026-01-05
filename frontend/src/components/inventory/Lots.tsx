import { useState, useEffect } from 'react'
import { getLots, getItems } from '../../api/inventory'
import './Lots.css'

function Lots() {
  const [lots, setLots] = useState<any[]>([])
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [lotsData, itemsData] = await Promise.all([getLots(), getItems()])
      setLots(lotsData)
      setItems(itemsData)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading lots...</div>
  }

  return (
    <div className="lots-container">
      <div className="lots-header">
        <h2>Lots</h2>
        <button className="btn btn-primary">+ Add Lot</button>
      </div>

      <div className="lots-table-container">
        <table className="lots-table">
          <thead>
            <tr>
              <th>Lot Number</th>
              <th>Item</th>
              <th>Quantity</th>
              <th>Remaining</th>
              <th>Received Date</th>
              <th>Expiration Date</th>
            </tr>
          </thead>
          <tbody>
            {lots.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  No lots found.
                </td>
              </tr>
            ) : (
              lots.map((lot) => (
                <tr key={lot.id}>
                  <td>{lot.lot_number}</td>
                  <td>{lot.item?.name || '-'}</td>
                  <td>{lot.quantity}</td>
                  <td>{lot.quantity_remaining}</td>
                  <td>{new Date(lot.received_date).toLocaleDateString()}</td>
                  <td>{lot.expiration_date ? new Date(lot.expiration_date).toLocaleDateString() : '-'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Lots

