import { useState, useEffect } from 'react'
import { getProductionBatches } from '../../api/inventory'
import BatchDetailView from './BatchDetailView'
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
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')

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

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, unit: string = 'lbs') => {
    if (unit === 'ea') return quantity.toFixed(0)
    if (unitDisplay === 'kg' && unit === 'lbs') {
      return (quantity * 0.453592).toFixed(2)
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      return (quantity * 2.20462).toFixed(2)
    }
    return quantity.toFixed(2)
  }

  const getDisplayUnit = (unit: string = 'lbs') => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  if (loading) {
    return <div className="loading">Loading production batches...</div>
  }

  return (
    <>
      {selectedBatchId && (
        <BatchDetailView
          batchId={selectedBatchId}
          onClose={() => setSelectedBatchId(null)}
        />
      )}
      <div className="batch-list-container">
      <div className="batch-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>In Progress</h2>
          <div className="unit-toggle">
            <label>Display Units:</label>
            <button
              className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
              onClick={() => setUnitDisplay('lbs')}
            >
              lbs
            </button>
            <button
              className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
              onClick={() => setUnitDisplay('kg')}
            >
              kg
            </button>
          </div>
        </div>
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
                  <td>{parseFloat(convertQuantity(batch.quantity_produced)).toLocaleString()} {getDisplayUnit()}</td>
                  <td>{new Date(batch.production_date).toLocaleDateString()}</td>
                  <td>
                    <span className={`status-badge status-${batch.status}`}>
                      {batch.status}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        onClick={() => setSelectedBatchId(batch.id)}
                        className="btn btn-info btn-sm"
                      >
                        View
                      </button>
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Closed Batches</h2>
        </div>
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
                  <td>{parseFloat(convertQuantity(batch.quantity_produced)).toLocaleString()} {getDisplayUnit()}</td>
                  <td>{parseFloat(convertQuantity(batch.quantity_actual)).toLocaleString()} {getDisplayUnit()}</td>
                  <td className={batch.variance >= 0 ? 'positive' : 'negative'}>
                    {batch.variance >= 0 ? '+' : ''}{parseFloat(convertQuantity(Math.abs(batch.variance))).toLocaleString()} {getDisplayUnit()}
                  </td>
                  <td>{parseFloat(convertQuantity(batch.wastes)).toLocaleString()} {getDisplayUnit()}</td>
                  <td>{parseFloat(convertQuantity(batch.spills)).toLocaleString()} {getDisplayUnit()}</td>
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
    </>
  )
}

export default ProductionBatchList

