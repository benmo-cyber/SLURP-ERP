import { useState, useEffect } from 'react'
import { getProductionBatch } from '../../api/inventory'
import { formatNumber, formatNumberFlexible } from '../../utils/formatNumber'
import './BatchDetailView.css'

interface Lot {
  id: number
  lot_number: string
  vendor_lot_number?: string
  quantity: number
  quantity_remaining: number
  received_date: string
  expiration_date?: string
  status: string
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
    item_type?: string
  }
}

interface ProductionBatchInput {
  id: number
  lot: Lot
  quantity_used: number
}

interface ProductionBatchOutput {
  id: number
  lot: Lot
  quantity_produced: number
}

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
  inputs: ProductionBatchInput[]
  outputs: ProductionBatchOutput[]
}

interface BatchDetailViewProps {
  batchId: number
  onClose: () => void
}

function BatchDetailView({ batchId, onClose }: BatchDetailViewProps) {
  const [batch, setBatch] = useState<ProductionBatch | null>(null)
  const [loading, setLoading] = useState(true)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')

  // Format production date to avoid timezone conversion issues
  const formatProductionDate = (dateString: string): string => {
    // Extract just the date part (YYYY-MM-DD) to avoid timezone conversion
    const datePart = dateString.split('T')[0]
    const [year, month, day] = datePart.split('-')
    return `${parseInt(month)}/${parseInt(day)}/${year}`
  }

  useEffect(() => {
    loadBatch()
  }, [batchId])

  const loadBatch = async () => {
    try {
      setLoading(true)
      const data = await getProductionBatch(batchId)
      setBatch(data)
    } catch (error) {
      console.error('Failed to load batch details:', error)
      alert('Failed to load batch details')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="batch-detail-overlay">
        <div className="batch-detail-container">
          <div className="loading">Loading batch details...</div>
        </div>
      </div>
    )
  }

  if (!batch) {
    return (
      <div className="batch-detail-overlay">
        <div className="batch-detail-container">
          <div className="error">Batch not found</div>
          <button onClick={onClose} className="btn btn-secondary">Close</button>
        </div>
      </div>
    )
  }

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, unit: string) => {
    // Preserve exact integers when displaying
    let displayValue = quantity
    
    if (unit === 'ea') {
      return formatNumber(quantity, 0)
    }
    
    if (unitDisplay === 'kg' && unit === 'lbs') {
      displayValue = quantity * 0.453592
    } else if (unitDisplay === 'lbs' && unit === 'kg') {
      displayValue = quantity * 2.20462
    }
    
    // Check if the result is effectively an integer (within floating point tolerance)
    // Use tolerance of 0.01 to catch floating point errors (e.g., 615.99 -> 616)
    const roundedToInteger = Math.round(displayValue)
    const isInteger = Math.abs(displayValue - roundedToInteger) <= 0.01
    
    if (isInteger) {
      // Use formatNumberFlexible to show integer without decimals
      return formatNumberFlexible(roundedToInteger, 0, 0)
    } else {
      return formatNumber(displayValue)
    }
  }

  const getDisplayUnit = (unit: string) => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  return (
    <div className="batch-detail-overlay">
      <div className="batch-detail-container">
        <div className="batch-detail-header">
          <h2>Batch Ticket Details: {batch.batch_number}</h2>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
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
            <button onClick={onClose} className="btn btn-secondary">← Back</button>
          </div>
        </div>

        <div className="batch-detail-content">
          <div className="batch-info-section">
            <h3>Batch Information</h3>
            <div className="info-grid">
              <div className="info-item">
                <label>Finished Good:</label>
                <span>{batch.finished_good_item.name} ({batch.finished_good_item.sku})</span>
              </div>
              <div className="info-item">
                <label>Status:</label>
                <span className={`status-badge status-${batch.status}`}>{batch.status}</span>
              </div>
              <div className="info-item">
                <label>Quantity to Produce:</label>
                <span>
                  {convertQuantity(batch.quantity_produced, batch.finished_good_item.unit_of_measure || 'lbs')} {getDisplayUnit(batch.finished_good_item.unit_of_measure || 'lbs')}
                </span>
              </div>
              {batch.status === 'closed' && (
                <>
                  <div className="info-item">
                    <label>Quantity Actual:</label>
                    <span>
                      {convertQuantity(batch.quantity_actual, batch.finished_good_item.unit_of_measure || 'lbs')} {getDisplayUnit(batch.finished_good_item.unit_of_measure || 'lbs')}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Variance:</label>
                    <span className={batch.variance >= 0 ? 'positive' : 'negative'}>
                      {batch.variance >= 0 ? '+' : ''}{convertQuantity(Math.abs(batch.variance), batch.finished_good_item.unit_of_measure || 'lbs')} {getDisplayUnit(batch.finished_good_item.unit_of_measure || 'lbs')}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Wastes:</label>
                    <span>
                      {convertQuantity(batch.wastes, batch.finished_good_item.unit_of_measure || 'lbs')} {getDisplayUnit(batch.finished_good_item.unit_of_measure || 'lbs')}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Spills:</label>
                    <span>
                      {convertQuantity(batch.spills, batch.finished_good_item.unit_of_measure || 'lbs')} {getDisplayUnit(batch.finished_good_item.unit_of_measure || 'lbs')}
                    </span>
                  </div>
                </>
              )}
              <div className="info-item">
                <label>Production Date:</label>
                <span>{formatProductionDate(batch.production_date)}</span>
              </div>
              {batch.closed_date && (
                <div className="info-item">
                  <label>Closed Date:</label>
                  <span>{new Date(batch.closed_date).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          </div>

          <div className="batch-inputs-section">
            <h3>Raw Material Lots Used</h3>
            {batch.inputs && batch.inputs.filter(input => input.lot.item.item_type !== 'indirect_material').length > 0 ? (
              <table className="batch-lots-table">
                <thead>
                  <tr>
                    <th>Lot Number</th>
                    <th>Vendor Lot Number</th>
                    <th>Item</th>
                    <th>SKU</th>
                    <th>Quantity Used</th>
                    <th>Unit</th>
                    <th>Received Date</th>
                    <th>Expiration Date</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.inputs.filter(input => input.lot.item.item_type !== 'indirect_material').map((input) => (
                    <tr key={input.id}>
                      <td>{input.lot.lot_number}</td>
                      <td>{input.lot.vendor_lot_number || 'N/A'}</td>
                      <td>{input.lot.item.name}</td>
                      <td>{input.lot.item.sku}</td>
                      <td>{convertQuantity(input.quantity_used, input.lot.item.unit_of_measure)}</td>
                      <td>{getDisplayUnit(input.lot.item.unit_of_measure)}</td>
                      <td>{new Date(input.lot.received_date).toLocaleDateString()}</td>
                      <td>{input.lot.expiration_date ? new Date(input.lot.expiration_date).toLocaleDateString() : 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">No raw material lots used</div>
            )}
          </div>

          {/* Indirect Materials Section */}
          {batch.inputs && batch.inputs.filter(input => input.lot.item.item_type === 'indirect_material').length > 0 && (
            <div className="batch-inputs-section" style={{ marginTop: '20px' }}>
              <h3>Indirect Materials Consumed</h3>
              <table className="batch-lots-table">
                <thead>
                  <tr>
                    <th>Lot Number</th>
                    <th>Item</th>
                    <th>SKU</th>
                    <th>Quantity Used</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.inputs.filter(input => input.lot.item.item_type === 'indirect_material').map((input) => (
                    <tr key={input.id}>
                      <td>{input.lot.lot_number}</td>
                      <td>{input.lot.item.name}</td>
                      <td>{input.lot.item.sku}</td>
                      <td>{convertQuantity(input.quantity_used, input.lot.item.unit_of_measure)}</td>
                      <td>{getDisplayUnit(input.lot.item.unit_of_measure)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {batch.outputs && batch.outputs.length > 0 && (
            <div className="batch-outputs-section">
              <h3>Output Lots Produced</h3>
              <table className="batch-lots-table">
                <thead>
                  <tr>
                    <th>Lot Number</th>
                    <th>Item</th>
                    <th>SKU</th>
                    <th>Quantity Produced</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.outputs.map((output) => (
                    <tr key={output.id}>
                      <td>{output.lot.lot_number}</td>
                      <td>{output.lot.item.name}</td>
                      <td>{output.lot.item.sku}</td>
                      <td>{convertQuantity(output.quantity_produced, output.lot.item.unit_of_measure)}</td>
                      <td>{getDisplayUnit(output.lot.item.unit_of_measure)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default BatchDetailView
