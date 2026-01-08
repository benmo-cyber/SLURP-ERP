import { useState, useEffect } from 'react'
import { getProductionBatches } from '../../api/inventory'
import './ProductionBatchList.css'

interface ProductionBatch {
  id: number
  batch_number: string
  finished_good_item: {
    id: number
    name: string
    sku: string
  }
  quantity_produced: number
  quantity_actual: number
  production_date: string
  closed_date: string | null
  status: string
  variance: number
  wastes: number
  spills: number
}

interface ProductionBatchListProps {
  onCloseBatch: (batch: ProductionBatch) => void
  onUnfkBatch?: (batch: ProductionBatch) => void
  onAdjustBatch?: (batch: ProductionBatch) => void
}

function ProductionBatchList({ onCloseBatch, onUnfkBatch, onAdjustBatch }: ProductionBatchListProps) {
  const [batches, setBatches] = useState<ProductionBatch[]>([])
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
      alert('Failed to load production batches')
    } finally {
      setLoading(false)
    }
  }

  const inProgressBatches = batches.filter(b => b.status === 'open' || b.status === 'in_progress')
  const closedBatches = batches.filter(b => b.status === 'closed')

  if (loading) {
    return <div className="loading">Loading production batches...</div>
  }

  return (
    <div className="batch-list-container">
      <div className="batch-section">
        <h2>In Progress</h2>
        {inProgressBatches.length === 0 ? (
          <div className="empty-state">No batches in progress</div>
        ) : (
          <table className="batch-table">
            <thead>
              <tr>
                <th>BT Number</th>
                <th>Finished Good</th>
                <th>Quantity to Produce</th>
                <th>Production Date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {inProgressBatches.map((batch) => (
                <tr key={batch.id}>
                  <td className="batch-number">{batch.batch_number}</td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{batch.quantity_produced.toLocaleString()} lbs</td>
                  <td>{new Date(batch.production_date).toLocaleDateString()}</td>
                  <td>
                    <span className={`status-badge status-${batch.status}`}>
                      {batch.status}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        onClick={() => onAdjustBatch?.(batch)}
                        className="btn btn-secondary btn-sm"
                      >
                        Adjust
                      </button>
                      <button
                        onClick={() => onCloseBatch(batch)}
                        className="btn btn-primary btn-sm"
                      >
                        Close Batch
                      </button>
                      <button
                        onClick={() => onUnfkBatch?.(batch)}
                        className="btn btn-danger btn-sm"
                      >
                        UNFK
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="batch-section">
        <h2>Closed Batches</h2>
        {closedBatches.length === 0 ? (
          <div className="empty-state">No closed batches</div>
        ) : (
          <table className="batch-table">
            <thead>
              <tr>
                <th>BT Number</th>
                <th>Finished Good</th>
                <th>Quantity Produced</th>
                <th>Quantity Actual</th>
                <th>Variance</th>
                <th>Wastes</th>
                <th>Spills</th>
                <th>Production Date</th>
                <th>Closed Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {closedBatches.map((batch) => (
                <tr key={batch.id}>
                  <td className="batch-number">{batch.batch_number}</td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{batch.quantity_produced.toLocaleString()} lbs</td>
                  <td>{batch.quantity_actual.toLocaleString()} lbs</td>
                  <td className={batch.variance >= 0 ? 'positive' : 'negative'}>
                    {batch.variance >= 0 ? '+' : ''}{batch.variance.toLocaleString()} lbs
                  </td>
                  <td>{batch.wastes.toLocaleString()} lbs</td>
                  <td>{batch.spills.toLocaleString()} lbs</td>
                  <td>{new Date(batch.production_date).toLocaleDateString()}</td>
                  <td>{batch.closed_date ? new Date(batch.closed_date).toLocaleDateString() : '-'}</td>
                  <td>
                    {onUnfkBatch && (
                      <button
                        onClick={() => onUnfkBatch(batch)}
                        className="btn btn-danger btn-sm"
                      >
                        UNFK
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default ProductionBatchList

