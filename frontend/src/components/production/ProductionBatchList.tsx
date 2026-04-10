import { useState, useEffect } from 'react'
import { getProductionBatches, updateProductionBatch } from '../../api/inventory'
import { useGodMode } from '../../context/GodModeContext'
import BatchDetailView from './BatchDetailView'
import { formatNumber } from '../../utils/formatNumber'
import { formatQuantityForDisplay, normalizeEaQuantity } from '../../utils/massQuantity'
import { formatAppDate } from '../../utils/appDateFormat'
import './ProductionBatchList.css'

const API_BASE_URL = 'http://localhost:8000/api'

interface ProductionBatch {
  id: number
  batch_number: string
  /** Production batches store mass in lbs; repack stores mass in the finished item native UoM (e.g. kg). */
  batch_type?: 'production' | 'repack'
  finished_good_item: {
    id: number
    name: string
    sku: string
    unit_of_measure?: string
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
  onReverseBatch?: (batch: ProductionBatch) => void
  onAdjustBatch?: (batch: ProductionBatch) => void
}

type InProgressSortKey = 'batch_number' | 'finished_good' | 'quantity_produced' | 'production_date' | 'status' | null
type ClosedSortKey = 'batch_number' | 'finished_good' | 'quantity_produced' | 'quantity_actual' | 'production_date' | 'closed_date' | 'status' | null

function ProductionBatchList({ onCloseBatch, onReverseBatch, onAdjustBatch }: ProductionBatchListProps) {
  const { godModeOn, canUseGodMode } = useGodMode()
  const allowBtEdit = Boolean(godModeOn && canUseGodMode)
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

  /** DB storage unit for batch-level mass fields: lbs for production, native UoM for repack. */
  const massStorageUnit = (batch: ProductionBatch): string => {
    if (batch.batch_type === 'repack') {
      const u = (batch.finished_good_item?.unit_of_measure || 'lbs').toLowerCase()
      if (u === 'ea') return 'ea'
      return u === 'kg' ? 'kg' : 'lbs'
    }
    return 'lbs'
  }

  // Convert quantity based on unit display preference (storage unit = API storage; normalize float drift)
  const convertQuantity = (quantity: number, storageUnit: string = 'lbs') => {
    if (storageUnit === 'ea') return formatNumber(normalizeEaQuantity(quantity), 0)
    return formatQuantityForDisplay(quantity, storageUnit, unitDisplay)
  }

  const getDisplayUnit = (storageUnit: string = 'lbs') => {
    if (storageUnit === 'ea') return 'ea'
    return unitDisplay
  }

  const formatQuantityToProduceColumn = (batch: ProductionBatch): string => {
    const su = massStorageUnit(batch)
    if (su === 'ea') return formatNumber(normalizeEaQuantity(batch.quantity_produced), 0)
    return formatQuantityForDisplay(batch.quantity_produced, su, unitDisplay)
  }

  const batchTicketPdfUrl = (batchId: number) =>
    `${API_BASE_URL}/production-batches/${batchId}/pdf/?mass_unit=${encodeURIComponent(unitDisplay)}`

  const saveBtNumber = async (batch: ProductionBatch, raw: string) => {
    const value = raw.trim()
    if (!value || value === batch.batch_number) return
    try {
      await updateProductionBatch(batch.id, { batch_number: value })
      await loadBatches()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      alert(e.response?.data?.error || (err instanceof Error ? err.message : 'Failed to update BT number'))
    }
  }

  const renderBtCell = (batch: ProductionBatch) => {
    const pdfUrl = batchTicketPdfUrl(batch.id)
    if (allowBtEdit) {
      return (
        <div className="batch-number-cell-god">
          <input
            type="text"
            className="batch-number-input"
            defaultValue={batch.batch_number}
            key={`${batch.id}-${batch.batch_number}`}
            title="God mode: edit BT number (staff). Blur or Enter to save."
            onBlur={(e) => saveBtNumber(batch, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
            }}
            aria-label="Batch ticket number"
          />
          <a
            href={pdfUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="batch-number-pdf-link"
            onClick={(e) => {
              e.preventDefault()
              window.open(pdfUrl, '_blank')
            }}
          >
            PDF
          </a>
        </div>
      )
    }
    if (batch.status === 'in_progress') {
      return (
        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#0066cc', textDecoration: 'underline', cursor: 'pointer' }}
          onClick={(e) => {
            e.preventDefault()
            window.open(pdfUrl, '_blank')
          }}
          title="Click to view/print batch ticket PDF (uses Display Units: lbs / kg)"
        >
          {batch.batch_number}
        </a>
      )
    }
    return <span>{batch.batch_number}</span>
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
                  <td className="batch-number">{renderBtCell(batch)}</td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{formatQuantityToProduceColumn(batch)} {getDisplayUnit(massStorageUnit(batch))}</td>
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
                        onClick={() => onReverseBatch?.(batch)}
                        title="Reverse this batch ticket: rolls back inventory effects and removes the batch (cannot be undone)"
                        className="btn btn-danger btn-sm"
                      >
                        Reverse batch
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
                  <td className="batch-number">{renderBtCell(batch)}</td>
                  <td>{batch.finished_good_item.name}</td>
                  <td>{convertQuantity(batch.quantity_produced, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}</td>
                  <td>{convertQuantity(batch.quantity_actual, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}</td>
                  <td className={batch.variance >= 0 ? 'positive' : 'negative'}>
                    {batch.variance >= 0 ? '+' : ''}{convertQuantity(Math.abs(batch.variance), massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
                  </td>
                  <td>{convertQuantity(batch.wastes, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}</td>
                  <td>{convertQuantity(batch.spills, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}</td>
                  <td>{formatProductionDate(batch.production_date)}</td>
                  <td>{batch.closed_date ? formatAppDate(batch.closed_date) : '-'}</td>
                  <td>
                    {onReverseBatch && (
                      <button
                        onClick={() => onReverseBatch(batch)}
                        title="Reverse this batch ticket: rolls back inventory effects and removes the batch (cannot be undone)"
                        className="btn btn-danger btn-sm"
                      >
                        Reverse batch
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

