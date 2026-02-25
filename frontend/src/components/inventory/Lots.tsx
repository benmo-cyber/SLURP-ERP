import { useState, useEffect } from 'react'
import { getLots, getItems } from '../../api/inventory'
import './Lots.css'

type LotsSortKey = 'lot_number' | 'item' | 'quantity' | 'quantity_remaining' | 'received_date' | 'expiration_date' | null

function Lots() {
  const [lots, setLots] = useState<any[]>([])
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<{ key: LotsSortKey; dir: 'asc' | 'desc' }>({ key: 'received_date', dir: 'desc' })

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

  const sortedLots = [...lots].sort((a, b) => {
    if (!sort.key) return 0
    let cmp = 0
    switch (sort.key) {
      case 'lot_number': cmp = (a.lot_number || '').localeCompare(b.lot_number || ''); break
      case 'item': cmp = (a.item?.name || '').localeCompare(b.item?.name || ''); break
      case 'quantity': cmp = (a.quantity ?? 0) - (b.quantity ?? 0); break
      case 'quantity_remaining': cmp = (a.quantity_remaining ?? 0) - (b.quantity_remaining ?? 0); break
      case 'received_date': cmp = new Date(a.received_date || 0).getTime() - new Date(b.received_date || 0).getTime(); break
      case 'expiration_date': cmp = new Date(a.expiration_date || 0).getTime() - new Date(b.expiration_date || 0).getTime(); break
      default: return 0
    }
    return sort.dir === 'asc' ? cmp : -cmp
  })

  const handleSort = (key: LotsSortKey) => {
    setSort(prev => ({ key: key!, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
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
              <th className="sortable" onClick={() => handleSort('lot_number')}>Lot Number {sort.key === 'lot_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('item')}>Item {sort.key === 'item' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('quantity')}>Quantity {sort.key === 'quantity' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('quantity_remaining')}>Remaining {sort.key === 'quantity_remaining' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('received_date')}>Received Date {sort.key === 'received_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('expiration_date')}>Expiration Date {sort.key === 'expiration_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
            </tr>
          </thead>
          <tbody>
            {sortedLots.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  No lots found.
                </td>
              </tr>
            ) : (
              sortedLots.map((lot) => (
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

