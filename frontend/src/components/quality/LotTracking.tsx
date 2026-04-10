import { useState, useEffect } from 'react'
import { getLots, getProductionBatches } from '../../api/inventory'
import { formatAppDate } from '../../utils/appDateFormat'
import './LotTracking.css'

interface Lot {
  id: number
  lot_number: string
  vendor_lot_number?: string
  item: {
    id: number
    name: string
    sku: string
  }
  quantity: number
  quantity_remaining: number
  received_date: string
}

interface ProductionBatch {
  id: number
  batch_number: string
  finished_good_item: {
    name: string
  }
  inputs: Array<{
    lot: {
      lot_number: string
    }
    quantity_used: number
  }>
  outputs: Array<{
    lot: {
      lot_number: string
    }
    quantity_produced: number
  }>
}

function LotTracking() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedLot, setSelectedLot] = useState<Lot | null>(null)
  const [forwardTrace, setForwardTrace] = useState<any[]>([])
  const [backwardTrace, setBackwardTrace] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const handleSearch = async () => {
    if (!searchTerm.trim()) {
      alert('Please enter a lot number to search')
      return
    }

    try {
      setLoading(true)
      const [lotsData, batchesData] = await Promise.all([
        getLots(),
        getProductionBatches()
      ])

      // Find lot by internal or vendor lot number
      const lot = lotsData.find((l: Lot) => 
        l.lot_number.toLowerCase() === searchTerm.toLowerCase().trim() ||
        (l.vendor_lot_number && l.vendor_lot_number.toLowerCase() === searchTerm.toLowerCase().trim())
      )

      if (!lot) {
        alert('Lot number not found')
        setSelectedLot(null)
        setForwardTrace([])
        setBackwardTrace([])
        return
      }

      setSelectedLot(lot)

      // Find forward traceability (where this lot was used)
      const forwardTraces: any[] = []
      batchesData.forEach((batch: ProductionBatch) => {
        batch.inputs?.forEach((input) => {
          if (input.lot.lot_number === lot.lot_number) {
            forwardTraces.push({
              type: 'used_in_production',
              batch_number: batch.batch_number,
              finished_good: batch.finished_good_item.name,
              quantity_used: input.quantity_used,
              date: batch.production_date,
            })
          }
        })
      })
      setForwardTrace(forwardTraces)

      // Find backward traceability (what was used to create this lot)
      const backwardTraces: any[] = []
      if (lot.item.item_type === 'finished_good') {
        // Find batches that produced this lot
        batchesData.forEach((batch: ProductionBatch) => {
          batch.outputs?.forEach((output) => {
            if (output.lot.lot_number === lot.lot_number) {
              backwardTraces.push({
                type: 'produced_by_batch',
                batch_number: batch.batch_number,
                quantity_produced: output.quantity_produced,
                date: batch.production_date,
                inputs: batch.inputs || [],
              })
            }
          })
        })
      }
      setBackwardTrace(backwardTraces)

    } catch (error) {
      console.error('Failed to search lot:', error)
      alert('Failed to search lot')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="lot-tracking">
      <div className="tracking-header">
        <h2>Lot Tracking & Traceability</h2>
        <p>Search by internal lot number or vendor lot number to track forwards and backwards</p>
      </div>

      <div className="search-section">
        <div className="search-box">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Enter lot number (internal or vendor lot number)"
            className="search-input"
          />
          <button onClick={handleSearch} className="btn btn-primary" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {selectedLot && (
        <div className="lot-details">
          <div className="lot-info-card">
            <h3>Lot Information</h3>
            <div className="info-grid">
              <div className="info-item">
                <label>Internal Lot Number:</label>
                <span className="lot-number">{selectedLot.lot_number}</span>
              </div>
              {selectedLot.vendor_lot_number && (
                <div className="info-item">
                  <label>Vendor Lot Number:</label>
                  <span>{selectedLot.vendor_lot_number}</span>
                </div>
              )}
              <div className="info-item">
                <label>Item:</label>
                <span>{selectedLot.item.name} ({selectedLot.item.sku})</span>
              </div>
              <div className="info-item">
                <label>Quantity:</label>
                <span>{selectedLot.quantity.toLocaleString()}</span>
              </div>
              <div className="info-item">
                <label>Quantity Remaining:</label>
                <span>{selectedLot.quantity_remaining.toLocaleString()}</span>
              </div>
              <div className="info-item">
                <label>Received Date:</label>
                <span>{formatAppDate(selectedLot.received_date)}</span>
              </div>
            </div>
          </div>

          <div className="traceability-section">
            <div className="trace-forward">
              <h3>Forward Traceability (Where Used)</h3>
              {forwardTrace.length === 0 ? (
                <div className="no-trace">This lot has not been used in any production batches</div>
              ) : (
                <table className="trace-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Batch Number</th>
                      <th>Finished Good</th>
                      <th>Quantity Used</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forwardTrace.map((trace, index) => (
                      <tr key={index}>
                        <td>Used in Production</td>
                        <td className="batch-number">{trace.batch_number}</td>
                        <td>{trace.finished_good}</td>
                        <td>{trace.quantity_used.toLocaleString()}</td>
                        <td>{formatAppDate(trace.date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="trace-backward">
              <h3>Backward Traceability (Source Materials)</h3>
              {backwardTrace.length === 0 ? (
                <div className="no-trace">This lot was not produced from other lots</div>
              ) : (
                backwardTrace.map((trace, index) => (
                  <div key={index} className="backward-trace-card">
                    <div className="trace-header">
                      <span className="batch-number">{trace.batch_number}</span>
                      <span>Produced: {trace.quantity_produced.toLocaleString()}</span>
                      <span>{formatAppDate(trace.date)}</span>
                    </div>
                    {trace.inputs.length > 0 && (
                      <div className="input-lots">
                        <h4>Source Lots:</h4>
                        <table className="trace-table">
                          <thead>
                            <tr>
                              <th>Source Lot Number</th>
                              <th>Quantity Used</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trace.inputs.map((input: any, idx: number) => (
                              <tr key={idx}>
                                <td className="lot-number">{input.lot.lot_number}</td>
                                <td>{input.quantity_used.toLocaleString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default LotTracking






