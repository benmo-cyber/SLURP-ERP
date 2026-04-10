import { useState, useEffect } from 'react'
import { getProductionBatches } from '../../api/inventory'
import { formatAppDate } from '../../utils/appDateFormat'
import './ProductionBatches.css'

function ProductionBatches() {
  const [batches, setBatches] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadBatches()
  }, [])

  const loadBatches = async () => {
    try {
      setLoading(true)
      const data = await getProductionBatches()
      setBatches(data)
    } catch (error) {
      console.error('Failed to load batches:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading production batches...</div>
  }

  return (
    <div className="batches-container">
      <div className="batches-header">
        <h2>Production Batches</h2>
        <button className="btn btn-primary">+ Add Batch</button>
      </div>

      <div className="batches-table-container">
        <table className="batches-table">
          <thead>
            <tr>
              <th>Batch Number</th>
              <th>Finished Good</th>
              <th>Quantity Produced</th>
              <th>Production Date</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {batches.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-state">
                  No production batches found.
                </td>
              </tr>
            ) : (
              batches.map((batch) => (
                <tr key={batch.id}>
                  <td>{batch.batch_number}</td>
                  <td>{batch.finished_good_item?.name || '-'}</td>
                  <td>{batch.quantity_produced}</td>
                  <td>{formatAppDate(batch.production_date)}</td>
                  <td>{batch.closed_date ? 'Closed' : 'Open'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default ProductionBatches

