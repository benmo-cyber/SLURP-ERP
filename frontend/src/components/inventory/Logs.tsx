import React, { useState, useEffect } from 'react'
import { getLotDepletionLogs, getPurchaseOrderLogs, getProductionLogs, LotDepletionLog, PurchaseOrderLog, ProductionLog } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './Logs.css'

interface LogsProps {
  defaultLogType?: 'depletion' | 'purchase-orders' | 'production'
}

function Logs({ defaultLogType = 'depletion' }: LogsProps) {
  const [activeLogType, setActiveLogType] = useState<'depletion' | 'purchase-orders' | 'production'>(defaultLogType)
  const [depletionLogs, setDepletionLogs] = useState<LotDepletionLog[]>([])
  const [poLogs, setPoLogs] = useState<PurchaseOrderLog[]>([])
  const [productionLogs, setProductionLogs] = useState<ProductionLog[]>([])
  const [loading, setLoading] = useState(true)
  
  const [depletionFilters, setDepletionFilters] = useState({
    lot_number: '',
    sku: '',
    method: '',
    date_from: '',
    date_to: ''
  })
  
  const [poFilters, setPoFilters] = useState({
    po_number: '',
    vendor: '',
    action: '',
    lot_number: '',
    date_from: '',
    date_to: ''
  })
  
  const [productionFilters, setProductionFilters] = useState({
    batch_number: '',
    sku: '',
    batch_type: '',
    date_from: '',
    date_to: ''
  })

  useEffect(() => {
    loadLogs()
  }, [activeLogType])

  const loadLogs = async () => {
    try {
      setLoading(true)
      if (activeLogType === 'depletion') {
        const activeFilters: any = {}
        if (depletionFilters.lot_number) activeFilters.lot_number = depletionFilters.lot_number
        if (depletionFilters.sku) activeFilters.sku = depletionFilters.sku
        if (depletionFilters.method) activeFilters.method = depletionFilters.method
        if (depletionFilters.date_from) activeFilters.date_from = depletionFilters.date_from
        if (depletionFilters.date_to) activeFilters.date_to = depletionFilters.date_to
        const data = await getLotDepletionLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setDepletionLogs(Array.isArray(data) ? data : [])
      } else if (activeLogType === 'purchase-orders') {
        const activeFilters: any = {}
        if (poFilters.po_number) activeFilters.po_number = poFilters.po_number
        if (poFilters.vendor) activeFilters.vendor = poFilters.vendor
        if (poFilters.action) activeFilters.action = poFilters.action
        if (poFilters.lot_number) activeFilters.lot_number = poFilters.lot_number
        if (poFilters.date_from) activeFilters.date_from = poFilters.date_from
        if (poFilters.date_to) activeFilters.date_to = poFilters.date_to
        const data = await getPurchaseOrderLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setPoLogs(Array.isArray(data) ? data : [])
      } else if (activeLogType === 'production') {
        const activeFilters: any = {}
        if (productionFilters.batch_number) activeFilters.batch_number = productionFilters.batch_number
        if (productionFilters.sku) activeFilters.sku = productionFilters.sku
        if (productionFilters.batch_type) activeFilters.batch_type = productionFilters.batch_type
        if (productionFilters.date_from) activeFilters.date_from = productionFilters.date_from
        if (productionFilters.date_to) activeFilters.date_to = productionFilters.date_to
        const data = await getProductionLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setProductionLogs(Array.isArray(data) ? data : [])
      }
    } catch (error: any) {
      console.error('Failed to load logs:', error)
      alert(`Failed to load logs: ${error.message || 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (type: 'depletion' | 'po' | 'production', field: string, value: string) => {
    if (type === 'depletion') {
      setDepletionFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'po') {
      setPoFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'production') {
      setProductionFilters(prev => ({ ...prev, [field]: value }))
    }
  }

  const handleApplyFilters = () => {
    loadLogs()
  }

  const handleClearFilters = () => {
    if (activeLogType === 'depletion') {
      setDepletionFilters({ lot_number: '', sku: '', method: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'purchase-orders') {
      setPoFilters({ po_number: '', vendor: '', action: '', lot_number: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'production') {
      setProductionFilters({ batch_number: '', sku: '', batch_type: '', date_from: '', date_to: '' })
    }
    setTimeout(loadLogs, 100)
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getMethodBadgeClass = (method: string) => {
    const classes: { [key: string]: string } = {
      'production': 'badge-production',
      'sales': 'badge-sales',
      'adjustment': 'badge-adjustment',
      'manual': 'badge-manual',
      'reversal': 'badge-reversal',
      'created': 'badge-created',
      'updated': 'badge-updated',
      'check_in': 'badge-check-in',
      'partial_check_in': 'badge-partial',
      'cancelled': 'badge-cancelled',
      'completed': 'badge-completed'
    }
    return classes[method] || 'badge-default'
  }

  if (loading) {
    return (
      <div className="logs-container">
        <div className="loading">Loading logs...</div>
      </div>
    )
  }

  return (
    <div className="logs-container">
      <div className="logs-header">
        <h2>System Logs</h2>
        <p className="subtitle">Track all system activities and transactions</p>
      </div>

      <div className="log-type-tabs">
        <button
          className={`log-type-tab ${activeLogType === 'depletion' ? 'active' : ''}`}
          onClick={() => setActiveLogType('depletion')}
        >
          Lot Depletion Logs
        </button>
        <button
          className={`log-type-tab ${activeLogType === 'purchase-orders' ? 'active' : ''}`}
          onClick={() => setActiveLogType('purchase-orders')}
        >
          Purchase Order Logs
        </button>
        <button
          className={`log-type-tab ${activeLogType === 'production' ? 'active' : ''}`}
          onClick={() => setActiveLogType('production')}
        >
          Production Logs
        </button>
      </div>

      {/* Depletion Logs */}
      {activeLogType === 'depletion' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>Lot Number</label>
                <input
                  type="text"
                  value={depletionFilters.lot_number}
                  onChange={(e) => handleFilterChange('depletion', 'lot_number', e.target.value)}
                  placeholder="Filter by lot number"
                />
              </div>
              <div className="filter-group">
                <label>SKU</label>
                <input
                  type="text"
                  value={depletionFilters.sku}
                  onChange={(e) => handleFilterChange('depletion', 'sku', e.target.value)}
                  placeholder="Filter by SKU"
                />
              </div>
              <div className="filter-group">
                <label>Depletion Method</label>
                <select
                  value={depletionFilters.method}
                  onChange={(e) => handleFilterChange('depletion', 'method', e.target.value)}
                >
                  <option value="">All Methods</option>
                  <option value="production">Production Batch</option>
                  <option value="sales">Sales Order</option>
                  <option value="adjustment">Inventory Adjustment</option>
                  <option value="manual">Manual Depletion</option>
                  <option value="reversal">Reversal/Cancellation</option>
                </select>
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={depletionFilters.date_from}
                  onChange={(e) => handleFilterChange('depletion', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={depletionFilters.date_to}
                  onChange={(e) => handleFilterChange('depletion', 'date_to', e.target.value)}
                />
              </div>
            </div>
            <div className="filter-actions">
              <button onClick={handleApplyFilters} className="btn-apply">Apply Filters</button>
              <button onClick={handleClearFilters} className="btn-clear">Clear Filters</button>
            </div>
          </div>

          <div className="logs-table-wrapper">
            <table className="logs-table">
              <thead>
                <tr>
                  <th>Depleted At</th>
                  <th>Lot Number</th>
                  <th>SKU</th>
                  <th>Item Name</th>
                  <th>Vendor</th>
                  <th>Initial Qty</th>
                  <th>Qty Before</th>
                  <th>Qty Used</th>
                  <th>Final Qty</th>
                  <th>Method</th>
                  <th>Reference</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {depletionLogs.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="no-data">No depletion logs found</td>
                  </tr>
                ) : (
                  depletionLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.depleted_at)}</td>
                      <td><strong>{log.lot_number}</strong></td>
                      <td>{log.item_sku}</td>
                      <td>{log.item_name}</td>
                      <td>{log.vendor || '-'}</td>
                      <td>{formatNumber(log.initial_quantity)}</td>
                      <td>{formatNumber(log.quantity_before)}</td>
                      <td className="quantity-used">{formatNumber(log.quantity_used)}</td>
                      <td className={log.final_quantity < 0 ? 'negative' : 'zero'}>
                        {formatNumber(log.final_quantity)}
                      </td>
                      <td>
                        <span className={`method-badge ${getMethodBadgeClass(log.depletion_method)}`}>
                          {log.depletion_method_display}
                        </span>
                      </td>
                      <td>{log.reference_number || '-'}</td>
                      <td className="notes-cell">{log.notes || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Purchase Order Logs */}
      {activeLogType === 'purchase-orders' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>PO Number</label>
                <input
                  type="text"
                  value={poFilters.po_number}
                  onChange={(e) => handleFilterChange('po', 'po_number', e.target.value)}
                  placeholder="Filter by PO number"
                />
              </div>
              <div className="filter-group">
                <label>Vendor</label>
                <input
                  type="text"
                  value={poFilters.vendor}
                  onChange={(e) => handleFilterChange('po', 'vendor', e.target.value)}
                  placeholder="Filter by vendor"
                />
              </div>
              <div className="filter-group">
                <label>Action</label>
                <select
                  value={poFilters.action}
                  onChange={(e) => handleFilterChange('po', 'action', e.target.value)}
                >
                  <option value="">All Actions</option>
                  <option value="created">Created</option>
                  <option value="updated">Updated</option>
                  <option value="check_in">Check-In</option>
                  <option value="partial_check_in">Partial Check-In</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="completed">Completed</option>
                </select>
              </div>
              <div className="filter-group">
                <label>Lot Number</label>
                <input
                  type="text"
                  value={poFilters.lot_number}
                  onChange={(e) => handleFilterChange('po', 'lot_number', e.target.value)}
                  placeholder="Filter by lot number"
                />
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={poFilters.date_from}
                  onChange={(e) => handleFilterChange('po', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={poFilters.date_to}
                  onChange={(e) => handleFilterChange('po', 'date_to', e.target.value)}
                />
              </div>
            </div>
            <div className="filter-actions">
              <button onClick={handleApplyFilters} className="btn-apply">Apply Filters</button>
              <button onClick={handleClearFilters} className="btn-clear">Clear Filters</button>
            </div>
          </div>

          <div className="logs-table-wrapper">
            <table className="logs-table">
              <thead>
                <tr>
                  <th>Logged At</th>
                  <th>PO Number</th>
                  <th>Action</th>
                  <th>Vendor</th>
                  <th>Status</th>
                  <th>Received Date</th>
                  <th>Lot Number</th>
                  <th>Item SKU</th>
                  <th>Item Name</th>
                  <th>Qty Received</th>
                  <th>Total Items</th>
                  <th>Total Ordered</th>
                  <th>Total Received</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {poLogs.length === 0 ? (
                  <tr>
                    <td colSpan={14} className="no-data">No purchase order logs found</td>
                  </tr>
                ) : (
                  poLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.logged_at)}</td>
                      <td><strong>{log.po_number}</strong></td>
                      <td>
                        <span className={`method-badge ${getMethodBadgeClass(log.action)}`}>
                          {log.action_display}
                        </span>
                      </td>
                      <td>{log.vendor_name || log.vendor_customer_name || '-'}</td>
                      <td>{log.status || '-'}</td>
                      <td>{log.po_received_date ? formatDate(log.po_received_date) : (log.received_date ? formatDate(log.received_date) : '-')}</td>
                      <td>{log.lot_number || '-'}</td>
                      <td>{log.item_sku || '-'}</td>
                      <td>{log.item_name || '-'}</td>
                      <td>{log.quantity_received ? formatNumber(log.quantity_received) : '-'}</td>
                      <td>{log.total_items}</td>
                      <td>{formatNumber(log.total_quantity_ordered)}</td>
                      <td>{formatNumber(log.total_quantity_received)}</td>
                      <td className="notes-cell">{log.notes || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Production Logs */}
      {activeLogType === 'production' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>Batch Number</label>
                <input
                  type="text"
                  value={productionFilters.batch_number}
                  onChange={(e) => handleFilterChange('production', 'batch_number', e.target.value)}
                  placeholder="Filter by batch number"
                />
              </div>
              <div className="filter-group">
                <label>SKU</label>
                <input
                  type="text"
                  value={productionFilters.sku}
                  onChange={(e) => handleFilterChange('production', 'sku', e.target.value)}
                  placeholder="Filter by SKU"
                />
              </div>
              <div className="filter-group">
                <label>Batch Type</label>
                <select
                  value={productionFilters.batch_type}
                  onChange={(e) => handleFilterChange('production', 'batch_type', e.target.value)}
                >
                  <option value="">All Types</option>
                  <option value="production">Production</option>
                  <option value="repack">Repack</option>
                </select>
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={productionFilters.date_from}
                  onChange={(e) => handleFilterChange('production', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={productionFilters.date_to}
                  onChange={(e) => handleFilterChange('production', 'date_to', e.target.value)}
                />
              </div>
            </div>
            <div className="filter-actions">
              <button onClick={handleApplyFilters} className="btn-apply">Apply Filters</button>
              <button onClick={handleClearFilters} className="btn-clear">Clear Filters</button>
            </div>
          </div>

          <div className="logs-table-wrapper">
            <table className="logs-table">
              <thead>
                <tr>
                  <th>Closed Date</th>
                  <th>Batch Number</th>
                  <th>Type</th>
                  <th>Finished Good SKU</th>
                  <th>Finished Good Name</th>
                  <th>Qty Produced</th>
                  <th>Qty Actual</th>
                  <th>Variance</th>
                  <th>Wastes</th>
                  <th>Spills</th>
                  <th>Output Lot</th>
                  <th>Production Date</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {productionLogs.length === 0 ? (
                  <tr>
                    <td colSpan={13} className="no-data">No production logs found</td>
                  </tr>
                ) : (
                  productionLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.closed_date)}</td>
                      <td><strong>{log.batch_number}</strong></td>
                      <td>{log.batch_type}</td>
                      <td>{log.finished_good_sku}</td>
                      <td>{log.finished_good_name}</td>
                      <td>{formatNumber(log.quantity_produced)}</td>
                      <td>{formatNumber(log.quantity_actual)}</td>
                      <td>{formatNumber(log.variance)}</td>
                      <td>{formatNumber(log.wastes)}</td>
                      <td>{formatNumber(log.spills)}</td>
                      <td>{log.output_lot_number || '-'}</td>
                      <td>{formatDate(log.production_date)}</td>
                      <td className="notes-cell">{log.notes || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="logs-summary">
        <p>Total {activeLogType === 'depletion' ? 'depletion' : activeLogType === 'purchase-orders' ? 'purchase order' : 'production'} logs: <strong>
          {activeLogType === 'depletion' ? depletionLogs.length : activeLogType === 'purchase-orders' ? poLogs.length : productionLogs.length}
        </strong></p>
      </div>
    </div>
  )
}

export default Logs
