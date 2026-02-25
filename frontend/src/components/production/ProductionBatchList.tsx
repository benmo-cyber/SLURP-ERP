import { useState, useEffect } from 'react'
import { getProductionBatches } from '../../api/inventory'
import BatchDetailView from './BatchDetailView'
import { formatNumber } from '../../utils/formatNumber'
import './ProductionBatchList.css'

const API_BASE_URL = 'http://localhost:8000/api'

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

type InProgressSortKey = 'batch_number' | 'finished_good' | 'quantity_produced' | 'production_date' | 'status' | null
type ClosedSortKey = 'batch_number' | 'finished_good' | 'quantity_produced' | 'quantity_actual' | 'production_date' | 'closed_date' | 'status' | null

function ProductionBatchList({ onCloseBatch, onUnfkBatch, onAdjustBatch }: ProductionBatchListProps) {
  const [batches, setBatches] = useState<ProductionBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [inProgressSort, setInProgressSort] = useState<{ key: InProgressSortKey; dir: 'asc' | 'desc' }>({ key: 'production_date', dir: 'desc' })
  const [closedSort, setClosedSort] = useState<{ key: ClosedSortKey; dir: 'asc' | 'desc' }>({ key: 'closed_date', dir: 'desc' })

  const sortInProgress = (list: ProductionBatch[]) => {
    if (!inProgressSort.key) return list
    return [...list].sort((a, b) => {
      let cmp = 0
      switch (inProgressSort.key) {
        case 'batch_number': cmp = (a.batch_number || '').localeCompare(b.batch_number || ''); break
        case 'finished_good': cmp = (a.finished_good_item?.name || '').localeCompare(b.finished_good_item?.name || ''); break
        case 'quantity_produced': cmp = a.quantity_produced - b.quantity_produced; break
        case 'production_date': cmp = new Date(a.production_date).getTime() - new Date(b.production_date).getTime(); break
        case 'status': cmp = (a.status || '').localeCompare(b.status || ''); break
        default: return 0
      }
      return inProgressSort.dir === 'asc' ? cmp : -cmp
    })
  }
  const sortClosed = (list: ProductionBatch[]) => {
    if (!closedSort.key) return list
    return [...list].sort((a, b) => {
      let cmp = 0
      switch (closedSort.key) {
        case 'batch_number': cmp = (a.batch_number || '').localeCompare(b.batch_number || ''); break
        case 'finished_good': cmp = (a.finished_good_item?.name || '').localeCompare(b.finished_good_item?.name || ''); break
        case 'quantity_produced': cmp = a.quantity_produced - b.quantity_produced; break
        case 'quantity_actual': cmp = a.quantity_actual - b.quantity_actual; break
        case 'production_date': cmp = new Date(a.production_date).getTime() - new Date(b.production_date).getTime(); break
        case 'closed_date': cmp = new Date(a.closed_date || 0).getTime() - new Date(b.closed_date || 0).getTime(); break
        case 'status': cmp = (a.status || '').localeCompare(b.status || ''); break
        default: return 0
      }
      return closedSort.dir === 'asc' ? cmp : -cmp
    })
  }

  const handleInProgressSort = (key: InProgressSortKey) => {
    setInProgressSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }
  const handleClosedSort = (key: ClosedSortKey) => {
    setClosedSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  // Format production date to avoid timezone conversion issues
  const formatProductionDate = (dateString: string): string => {
    // Extract just the date part (YYYY-MM-DD) to avoid timezone conversion
    const datePart = dateString.split('T')[0]
    const [year, month, day] = datePart.split('-')
    return `${parseInt(month)}/${parseInt(day)}/${year}`
  }

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

  // Include draft, scheduled, and in_progress so no batches go "missing" (backend never uses 'open')
  const inProgressBatches = batches.filter(b => b.status !== 'closed')
  const closedBatches = batches.filter(b => b.status === 'closed')

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, unit: string = 'lbs') => {
    if (unit === 'ea') return formatNumber(quantity, 0)
    if (unitDisplay === 'kg' && unit === 'lbs') {
      return formatNumber(quantity * 0.453592)
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      return formatNumber(quantity * 2.20462)
    }
    return formatNumber(quantity)
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
                <th className="sortable" onClick={() => handleInProgressSort('batch_number')}>BT Number {inProgressSort.key === 'batch_number' && (inProgressSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleInProgressSort('finished_good')}>Finished Good {inProgressSort.key === 'finished_good' && (inProgressSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleInProgressSort('quantity_produced')}>Quantity to Produce {inProgressSort.key === 'quantity_produced' && (inProgressSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleInProgressSort('production_date')}>Production Date {inProgressSort.key === 'production_date' && (inProgressSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleInProgressSort('status')}>Status {inProgressSort.key === 'status' && (inProgressSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortInProgress(inProgressBatches).map((batch) => (
                <tr key={batch.id}>
                  <td className="batch-number">
                    {batch.status === 'in_progress' ? (
                      <a
                        href={`${API_BASE_URL}/production-batches/${batch.id}/pdf/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: '#0066cc', textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.preventDefault()
                          window.open(`${API_BASE_URL}/production-batches/${batch.id}/pdf/`, '_blank')
                        }}
                        title="Click to view/print batch ticket PDF"
                      >
                        {batch.batch_number}
                      </a>
                    ) : (
                      batch.batch_number
                    )}
                  </td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{convertQuantity(batch.quantity_produced)} {getDisplayUnit()}</td>
                  <td>{formatProductionDate(batch.production_date)}</td>
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
                <th className="sortable" onClick={() => handleClosedSort('batch_number')}>BT Number {closedSort.key === 'batch_number' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleClosedSort('finished_good')}>Finished Good {closedSort.key === 'finished_good' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleClosedSort('quantity_produced')}>Qty Produced {closedSort.key === 'quantity_produced' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleClosedSort('quantity_actual')}>Qty Actual {closedSort.key === 'quantity_actual' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th>Variance</th>
                <th>Wastes</th>
                <th>Spills</th>
                <th className="sortable" onClick={() => handleClosedSort('production_date')}>Production Date {closedSort.key === 'production_date' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th className="sortable" onClick={() => handleClosedSort('closed_date')}>Closed Date {closedSort.key === 'closed_date' && (closedSort.dir === 'asc' ? '↑' : '↓')}</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortClosed(closedBatches).map((batch) => (
                <tr key={batch.id}>
                  <td className="batch-number">
                    <a
                      href={`${API_BASE_URL}/production-batches/${batch.id}/pdf/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#0066cc', textDecoration: 'underline', cursor: 'pointer' }}
                      onClick={(e) => {
                        e.preventDefault()
                        window.open(`${API_BASE_URL}/production-batches/${batch.id}/pdf/`, '_blank')
                      }}
                      title="Click to view/print batch ticket PDF"
                    >
                      {batch.batch_number}
                    </a>
                  </td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{convertQuantity(batch.quantity_produced)} {getDisplayUnit()}</td>
                  <td>{convertQuantity(batch.quantity_actual)} {getDisplayUnit()}</td>
                  <td className={batch.variance >= 0 ? 'positive' : 'negative'}>
                    {batch.variance >= 0 ? '+' : ''}{convertQuantity(Math.abs(batch.variance))} {getDisplayUnit()}
                  </td>
                  <td>{convertQuantity(batch.wastes)} {getDisplayUnit()}</td>
                  <td>{convertQuantity(batch.spills)} {getDisplayUnit()}</td>
                  <td>{formatProductionDate(batch.production_date)}</td>
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

