import { useState, useEffect } from 'react'
import { getItems, getLots } from '../../api/inventory'
import './InventorySummary.css'

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  item_type: string
  unit_of_measure: string
  vendor?: string
}

interface Lot {
  id: number
  lot_number: string
  item: Item
  quantity: number
  quantity_remaining: number
  received_date: string
  expiration_date?: string
}

function InventorySummary() {
  const [items, setItems] = useState<Item[]>([])
  const [lots, setLots] = useState<Lot[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [itemsData, lotsData] = await Promise.all([getItems(), getLots()])
      setItems(itemsData)
      setLots(lotsData)
    } catch (error) {
      console.error('Failed to load inventory:', error)
      alert('Failed to load inventory data. Make sure the backend server is running.')
    } finally {
      setLoading(false)
    }
  }

  // Calculate total quantity for each item
  const getItemTotalQuantity = (itemId: number) => {
    return lots
      .filter(lot => lot.item.id === itemId)
      .reduce((sum, lot) => sum + lot.quantity_remaining, 0)
  }

  // Get lots for an item
  const getItemLots = (itemId: number) => {
    return lots.filter(lot => lot.item.id === itemId)
  }

  if (loading) {
    return <div className="loading">Loading inventory...</div>
  }

  return (
    <div className="inventory-summary">
      <div className="summary-header">
        <h2>Company Inventory</h2>
        <button onClick={loadData} className="btn btn-secondary">Refresh</button>
      </div>

      <div className="inventory-items">
        {items.length === 0 ? (
          <div className="empty-state">
            <p>No inventory items found.</p>
            <p>Use the "Check In" tab to add materials to inventory.</p>
          </div>
        ) : (
          items.map((item) => {
            const totalQty = getItemTotalQuantity(item.id)
            const itemLots = getItemLots(item.id)
            
            return (
              <div key={item.id} className="inventory-item-card">
                <div className="item-header">
                  <div className="item-info">
                    <h3>{item.name}</h3>
                    <div className="item-details">
                      <span className="item-sku">SKU: {item.sku}</span>
                      <span className="item-type">{item.item_type.replace('_', ' ')}</span>
                      {item.vendor && <span className="item-vendor">Vendor: {item.vendor}</span>}
                    </div>
                  </div>
                  <div className="item-total">
                    <div className="total-quantity">{totalQty.toLocaleString()}</div>
                    <div className="total-unit">{item.unit_of_measure}</div>
                  </div>
                </div>
                
                {item.description && (
                  <div className="item-description">{item.description}</div>
                )}

                {itemLots.length > 0 && (
                  <div className="item-lots">
                    <h4>Lots:</h4>
                    <table className="lots-table">
                      <thead>
                        <tr>
                          <th>Lot Number</th>
                          <th>Quantity</th>
                          <th>Remaining</th>
                          <th>Received Date</th>
                          <th>Expiration Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {itemLots.map((lot) => (
                          <tr key={lot.id}>
                            <td>{lot.lot_number}</td>
                            <td>{lot.quantity.toLocaleString()}</td>
                            <td>{lot.quantity_remaining.toLocaleString()}</td>
                            <td>{new Date(lot.received_date).toLocaleDateString()}</td>
                            <td>{lot.expiration_date ? new Date(lot.expiration_date).toLocaleDateString() : '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default InventorySummary

