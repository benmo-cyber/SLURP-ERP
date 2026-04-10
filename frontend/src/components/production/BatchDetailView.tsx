import { useState, useEffect } from 'react'
import {
  getProductionBatch,
  updateProductionBatch,
  getCampaignLots,
  createCampaignLot,
  type CampaignLot,
} from '../../api/inventory'
import { useGodMode } from '../../context/GodModeContext'
import { formatNumber } from '../../utils/formatNumber'
import { formatQuantityForDisplay, normalizeEaQuantity } from '../../utils/massQuantity'
import { formatAppDate } from '../../utils/appDateFormat'
import './BatchDetailView.css'

const API_BASE_URL = 'http://localhost:8000/api'

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
  /** Production: batch-level mass is stored in lbs. Repack: stored in item native UoM (e.g. kg). */
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
  inputs: ProductionBatchInput[]
  outputs: ProductionBatchOutput[]
  campaign?: CampaignLot | null
}

interface BatchDetailViewProps {
  batchId: number
  onClose: () => void
}

function BatchDetailView({ batchId, onClose }: BatchDetailViewProps) {
  const { canUseGodMode, godModeOn } = useGodMode()
  const allowBtEdit = canUseGodMode && godModeOn
  const [batch, setBatch] = useState<ProductionBatch | null>(null)
  const [loading, setLoading] = useState(true)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [campaignOptions, setCampaignOptions] = useState<CampaignLot[]>([])
  const [campaignSelectId, setCampaignSelectId] = useState<string>('')
  const [newAnchorDate, setNewAnchorDate] = useState('')
  const [newProductCode, setNewProductCode] = useState('')
  const [campaignBusy, setCampaignBusy] = useState(false)

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
      const itemId = data.finished_good_item?.id
      if (itemId) {
        const list = await getCampaignLots(itemId)
        setCampaignOptions(list)
        const cid = data.campaign?.id
        setCampaignSelectId(cid != null ? String(cid) : '')
        const pd = (data.production_date || '').split('T')[0]
        setNewAnchorDate(pd || '')
      }
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

  const massStorageUnit = (b: ProductionBatch): string => {
    if (b.batch_type === 'repack') {
      const u = (b.finished_good_item.unit_of_measure || 'lbs').toLowerCase()
      if (u === 'ea') return 'ea'
      return u === 'kg' ? 'kg' : 'lbs'
    }
    return 'lbs'
  }

  const convertQuantity = (quantity: number, unit: string) => {
    if (unit === 'ea') return formatNumber(normalizeEaQuantity(quantity), 0)
    return formatQuantityForDisplay(quantity, unit, unitDisplay)
  }

  const getDisplayUnit = (unit: string) => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  const batchTicketPdfUrl = `${API_BASE_URL}/production-batches/${batch.id}/pdf/?mass_unit=${encodeURIComponent(unitDisplay)}`

  const saveBtNumber = async (raw: string) => {
    const value = raw.trim()
    if (!value || value === batch.batch_number) return
    try {
      await updateProductionBatch(batch.id, { batch_number: value })
      await loadBatch()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } }
      alert(e.response?.data?.error || (err instanceof Error ? err.message : 'Failed to update BT number'))
    }
  }

  const formatCampaignError = (err: unknown, fallback: string): string => {
    const e = err as { response?: { data?: Record<string, unknown> } }
    const d = e.response?.data
    if (d && typeof d === 'object') {
      if (typeof d.detail === 'string') return d.detail
      const cid = d.campaign_id
      if (Array.isArray(cid) && cid[0]) return String(cid[0])
      if (typeof cid === 'string') return cid
      const n = d.non_field_errors
      if (Array.isArray(n) && n[0]) return String(n[0])
      if (typeof n === 'string') return n
    }
    return err instanceof Error ? err.message : fallback
  }

  const assignCampaign = async (campaignId: number | null) => {
    if (!batch) return
    setCampaignBusy(true)
    try {
      await updateProductionBatch(batch.id, { campaign_id: campaignId })
      await loadBatch()
    } catch (err: unknown) {
      alert(formatCampaignError(err, 'Failed to update campaign assignment'))
    } finally {
      setCampaignBusy(false)
    }
  }

  const createAndAssignCampaign = async () => {
    if (!batch) return
    const code = newProductCode.trim()
    if (!newAnchorDate || !code) {
      alert('Enter anchor date and product code for the new campaign.')
      return
    }
    setCampaignBusy(true)
    try {
      const created = await createCampaignLot({
        item: batch.finished_good_item.id,
        anchor_date: newAnchorDate,
        product_code: code,
      })
      await updateProductionBatch(batch.id, { campaign_id: created.id })
      await loadBatch()
      setNewProductCode('')
    } catch (err: unknown) {
      alert(formatCampaignError(err, 'Failed to create campaign'))
    } finally {
      setCampaignBusy(false)
    }
  }

  return (
    <div className="batch-detail-overlay">
      <div className="batch-detail-container">
        <div className="batch-detail-header">
          <h2 className="batch-detail-title">
            Batch Ticket Details:{' '}
            {allowBtEdit ? (
              <input
                type="text"
                className="batch-detail-bt-input"
                defaultValue={batch.batch_number}
                key={batch.batch_number}
                title="God mode: edit BT number (staff). Blur or Enter to save."
                onBlur={(e) => saveBtNumber(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                }}
                aria-label="Batch ticket number"
              />
            ) : (
              batch.batch_number
            )}
          </h2>
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
            <a
              href={batchTicketPdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
              title="Batch ticket PDF (matches Display Units: lbs / kg)"
            >
              PDF
            </a>
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
                  {convertQuantity(batch.quantity_produced, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
                </span>
              </div>
              {batch.status === 'closed' && (
                <>
                  <div className="info-item">
                    <label>Quantity Actual:</label>
                    <span>
                      {convertQuantity(batch.quantity_actual, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Variance:</label>
                    <span className={batch.variance >= 0 ? 'positive' : 'negative'}>
                      {batch.variance >= 0 ? '+' : ''}{convertQuantity(Math.abs(batch.variance), massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Wastes:</label>
                    <span>
                      {convertQuantity(batch.wastes, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
                    </span>
                  </div>
                  <div className="info-item">
                    <label>Spills:</label>
                    <span>
                      {convertQuantity(batch.spills, massStorageUnit(batch))} {getDisplayUnit(massStorageUnit(batch))}
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
                  <span>{formatAppDate(batch.closed_date)}</span>
                </div>
              )}
              <div className="info-item" style={{ gridColumn: '1 / -1' }}>
                <label>Campaign lot code:</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '4px' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{batch.campaign?.campaign_code || '—'}</span>
                    <select
                      value={campaignSelectId}
                      onChange={(e) => setCampaignSelectId(e.target.value)}
                      disabled={campaignBusy}
                      aria-label="Assign existing campaign"
                    >
                      <option value="">(none)</option>
                      {campaignOptions.map((c) => (
                        <option key={c.id} value={String(c.id)}>
                          {c.campaign_code}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={campaignBusy}
                      onClick={() => {
                        const v = campaignSelectId.trim()
                        void assignCampaign(v ? parseInt(v, 10) : null)
                      }}
                    >
                      Apply
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={campaignBusy || !batch.campaign}
                      onClick={() => void assignCampaign(null)}
                    >
                      Clear
                    </button>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                    <span style={{ marginRight: '4px', fontSize: '0.85rem', color: '#444' }}>
                      New campaign (ISO week from date + product code):
                    </span>
                    <input
                      type="date"
                      value={newAnchorDate}
                      onChange={(e) => setNewAnchorDate(e.target.value)}
                      disabled={campaignBusy}
                      aria-label="Campaign anchor date"
                    />
                    <input
                      type="text"
                      value={newProductCode}
                      onChange={(e) => setNewProductCode(e.target.value)}
                      placeholder="e.g. D1307"
                      disabled={campaignBusy}
                      style={{ width: '7rem' }}
                      aria-label="Product code suffix"
                    />
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={campaignBusy}
                      onClick={() => void createAndAssignCampaign()}
                    >
                      Create &amp; assign
                    </button>
                  </div>
                </div>
              </div>
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
                      <td>{formatAppDate(input.lot.received_date)}</td>
                      <td>{input.lot.expiration_date ? formatAppDate(input.lot.expiration_date) : 'N/A'}</td>
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
