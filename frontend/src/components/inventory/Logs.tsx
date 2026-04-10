import React, { useState, useEffect } from 'react'
import { getLotDepletionLogs, getLotTransactionLogs, getPurchaseOrderLogs, getProductionLogs, getCheckInLogs, getLotAttributeChangeLogs, LotDepletionLog, LotTransactionLog, PurchaseOrderLog, ProductionLog, CheckInLog, LotAttributeChangeLog } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import { formatAppDate, formatAppDateTime } from '../../utils/appDateFormat'
import './Logs.css'

interface LogsProps {
  defaultLogType?: 'depletion' | 'transactions' | 'purchase-orders' | 'production' | 'check-ins' | 'lot-attribute-changes'
}

function Logs({ defaultLogType = 'transactions' }: LogsProps) {
  const [activeLogType, setActiveLogType] = useState<
    'depletion' | 'transactions' | 'purchase-orders' | 'production' | 'check-ins' | 'lot-attribute-changes'
  >(defaultLogType)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [depletionLogs, setDepletionLogs] = useState<LotDepletionLog[]>([])
  const [transactionLogs, setTransactionLogs] = useState<LotTransactionLog[]>([])
  const [poLogs, setPoLogs] = useState<PurchaseOrderLog[]>([])
  const [productionLogs, setProductionLogs] = useState<ProductionLog[]>([])
  const [checkInLogs, setCheckInLogs] = useState<CheckInLog[]>([])
  const [lotAttributeChangeLogs, setLotAttributeChangeLogs] = useState<LotAttributeChangeLog[]>([])
  const [loading, setLoading] = useState(true)
  
  const [depletionFilters, setDepletionFilters] = useState({
    lot_number: '',
    sku: '',
    method: '',
    date_from: '',
    date_to: ''
  })
  
  const [transactionFilters, setTransactionFilters] = useState({
    lot_number: '',
    sku: '',
    transaction_type: '',
    reference_number: '',
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
  
  const [checkInFilters, setCheckInFilters] = useState({
    item_sku: '',
    po_number: '',
    date_from: '',
    date_to: ''
  })

  const [lotAttributeFilters, setLotAttributeFilters] = useState({
    lot_number: '',
    sku: '',
    field_name: '',
    date_from: '',
    date_to: ''
  })
  
  // Unit conversion helper
  const convertQuantity = (quantity: number, fromUnit: 'lbs' | 'kg' | 'ea', toUnit: 'lbs' | 'kg'): number => {
    if (fromUnit === 'ea' || toUnit === 'ea') return quantity
    if (fromUnit === toUnit) return quantity
    if (fromUnit === 'lbs' && toUnit === 'kg') return quantity * 0.453592
    if (fromUnit === 'kg' && toUnit === 'lbs') return quantity * 2.20462
    return quantity
  }

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
      } else if (activeLogType === 'check-ins') {
        const activeFilters: any = {}
        if (checkInFilters.item_sku) activeFilters.item_sku = checkInFilters.item_sku
        if (checkInFilters.po_number) activeFilters.po_number = checkInFilters.po_number
        if (checkInFilters.date_from) activeFilters.date_from = checkInFilters.date_from
        if (checkInFilters.date_to) activeFilters.date_to = checkInFilters.date_to
        const data = await getCheckInLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setCheckInLogs(Array.isArray(data) ? data : [])
      } else if (activeLogType === 'lot-attribute-changes') {
        const activeFilters: any = {}
        if (lotAttributeFilters.lot_number) activeFilters.lot_number = lotAttributeFilters.lot_number
        if (lotAttributeFilters.sku) activeFilters.sku = lotAttributeFilters.sku
        if (lotAttributeFilters.field_name) activeFilters.field_name = lotAttributeFilters.field_name
        if (lotAttributeFilters.date_from) activeFilters.date_from = lotAttributeFilters.date_from
        if (lotAttributeFilters.date_to) activeFilters.date_to = lotAttributeFilters.date_to
        const data = await getLotAttributeChangeLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setLotAttributeChangeLogs(Array.isArray(data) ? data : [])
      } else if (activeLogType === 'transactions') {
        const activeFilters: any = {}
        if (transactionFilters.lot_number) activeFilters.lot_number = transactionFilters.lot_number
        if (transactionFilters.sku) activeFilters.sku = transactionFilters.sku
        if (transactionFilters.transaction_type) activeFilters.transaction_type = transactionFilters.transaction_type
        if (transactionFilters.reference_number) activeFilters.reference_number = transactionFilters.reference_number
        if (transactionFilters.date_from) activeFilters.date_from = transactionFilters.date_from
        if (transactionFilters.date_to) activeFilters.date_to = transactionFilters.date_to
        const data = await getLotTransactionLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
        setTransactionLogs(Array.isArray(data) ? data : [])
      }
    } catch (error: any) {
      console.error('Failed to load logs:', error)
      alert(`Failed to load logs: ${error.message || 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (
    type: 'depletion' | 'transactions' | 'po' | 'production' | 'check-ins' | 'lot-attribute-changes',
    field: string,
    value: string
  ) => {
    if (type === 'depletion') {
      setDepletionFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'transactions') {
      setTransactionFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'po') {
      setPoFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'production') {
      setProductionFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'check-ins') {
      setCheckInFilters(prev => ({ ...prev, [field]: value }))
    } else if (type === 'lot-attribute-changes') {
      setLotAttributeFilters(prev => ({ ...prev, [field]: value }))
    }
  }

  const handleApplyFilters = () => {
    loadLogs()
  }

  const handleClearFilters = () => {
    if (activeLogType === 'transactions') {
      setTransactionFilters({ lot_number: '', sku: '', transaction_type: '', reference_number: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'depletion') {
      setDepletionFilters({ lot_number: '', sku: '', method: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'purchase-orders') {
      setPoFilters({ po_number: '', vendor: '', action: '', lot_number: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'production') {
      setProductionFilters({ batch_number: '', sku: '', batch_type: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'check-ins') {
      setCheckInFilters({ item_sku: '', po_number: '', date_from: '', date_to: '' })
    } else if (activeLogType === 'lot-attribute-changes') {
      setLotAttributeFilters({ lot_number: '', sku: '', field_name: '', date_from: '', date_to: '' })
    }
    setTimeout(loadLogs, 100)
  }

  const formatDate = (dateString: string) => formatAppDateTime(dateString)

  const getMethodBadgeClass = (method: string) => {
    const classes: { [key: string]: string } = {
      'production': 'badge-production',
      'sales': 'badge-sales',
      'adjustment': 'badge-adjustment',
      'manual': 'badge-manual',
      'reversal': 'badge-reversal',
      'receipt': 'badge-receipt',
      'production_input': 'badge-production',
      'production_output': 'badge-production',
      'allocation': 'badge-allocation',
      'deallocation': 'badge-deallocation',
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
        <div>
          <h2>System Logs</h2>
          <p className="subtitle">Track all system activities and transactions</p>
        </div>
        <div className="unit-toggle">
          <label>Unit of Measure:</label>
          <button
            className={`unit-toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('lbs')}
          >
            lbs
          </button>
          <button
            className={`unit-toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('kg')}
          >
            kg
          </button>
        </div>
      </div>

      <div className="log-type-tabs">
        <button
          className={`log-type-tab ${activeLogType === 'transactions' ? 'active' : ''}`}
          onClick={() => setActiveLogType('transactions')}
        >
          Transaction Logs
        </button>
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
        <button
          className={`log-type-tab ${activeLogType === 'check-ins' ? 'active' : ''}`}
          onClick={() => setActiveLogType('check-ins')}
        >
          Check-In Logs
        </button>
        <button
          className={`log-type-tab ${activeLogType === 'lot-attribute-changes' ? 'active' : ''}`}
          onClick={() => setActiveLogType('lot-attribute-changes')}
        >
          Lot field changes
        </button>
      </div>

      {/* Transaction Logs */}
      {activeLogType === 'transactions' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>Lot Number</label>
                <input
                  type="text"
                  value={transactionFilters.lot_number}
                  onChange={(e) => handleFilterChange('transactions', 'lot_number', e.target.value)}
                  placeholder="Filter by lot number"
                />
              </div>
              <div className="filter-group">
                <label>SKU</label>
                <input
                  type="text"
                  value={transactionFilters.sku}
                  onChange={(e) => handleFilterChange('transactions', 'sku', e.target.value)}
                  placeholder="Filter by SKU"
                />
              </div>
              <div className="filter-group">
                <label>Transaction Type</label>
                <select
                  value={transactionFilters.transaction_type}
                  onChange={(e) => handleFilterChange('transactions', 'transaction_type', e.target.value)}
                >
                  <option value="">All Types</option>
                  <option value="receipt">Receipt</option>
                  <option value="production_input">Production Input</option>
                  <option value="production_output">Production Output</option>
                  <option value="sale">Sale</option>
                  <option value="adjustment">Adjustment</option>
                  <option value="allocation">Allocation</option>
                  <option value="deallocation">Deallocation</option>
                  <option value="manual">Manual</option>
                  <option value="reversal">Reversal</option>
                </select>
              </div>
              <div className="filter-group">
                <label>Reference Number</label>
                <input
                  type="text"
                  value={transactionFilters.reference_number}
                  onChange={(e) => handleFilterChange('transactions', 'reference_number', e.target.value)}
                  placeholder="PO, Batch, SO number"
                />
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={transactionFilters.date_from}
                  onChange={(e) => handleFilterChange('transactions', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={transactionFilters.date_to}
                  onChange={(e) => handleFilterChange('transactions', 'date_to', e.target.value)}
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
                  <th>Lot Number</th>
                  <th>SKU</th>
                  <th>Item Name</th>
                  <th>Transaction Type</th>
                  <th>Qty Before ({unitDisplay})</th>
                  <th>Qty Change ({unitDisplay})</th>
                  <th>Qty After ({unitDisplay})</th>
                  <th>Reference</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {transactionLogs.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="no-data">No transaction logs found</td>
                  </tr>
                ) : (
                  transactionLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.logged_at)}</td>
                      <td><strong>{log.lot_number}</strong></td>
                      <td>{log.item_sku}</td>
                      <td>{log.item_name}</td>
                      <td>
                        <span className={`method-badge ${getMethodBadgeClass(log.transaction_type)}`}>
                          {log.transaction_type_display}
                        </span>
                      </td>
                      <td>{formatNumber(convertQuantity(log.quantity_before, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td className={log.quantity_change >= 0 ? 'quantity-positive' : 'quantity-negative'}>
                        {log.quantity_change >= 0 ? '+' : ''}{formatNumber(convertQuantity(Math.abs(log.quantity_change), (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}
                      </td>
                      <td>{formatNumber(convertQuantity(log.quantity_after, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
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
                  <th>Initial Qty ({unitDisplay})</th>
                  <th>Qty Before ({unitDisplay})</th>
                  <th>Qty Used ({unitDisplay})</th>
                  <th>Final Qty ({unitDisplay})</th>
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
                      <td>{formatNumber(convertQuantity(log.initial_quantity, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td>{formatNumber(convertQuantity(log.quantity_before, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td className="quantity-used">{formatNumber(convertQuantity(log.quantity_used, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td className={log.final_quantity < 0 ? 'negative' : 'zero'}>
                        {formatNumber(convertQuantity(log.final_quantity, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}
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
                  <th>Qty Produced ({unitDisplay})</th>
                  <th>Qty Actual ({unitDisplay})</th>
                  <th>Variance ({unitDisplay})</th>
                  <th>Wastes ({unitDisplay})</th>
                  <th>Spills ({unitDisplay})</th>
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
                      <td>{formatNumber(convertQuantity(log.quantity_produced, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td>{formatNumber(convertQuantity(log.quantity_actual, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td>{formatNumber(convertQuantity(log.variance, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td>{formatNumber(convertQuantity(log.wastes, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
                      <td>{formatNumber(convertQuantity(log.spills, (log as any).unit_of_measure || 'lbs', unitDisplay))} {unitDisplay}</td>
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

      {/* Check-In Logs */}
      {activeLogType === 'check-ins' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>Item SKU</label>
                <input
                  type="text"
                  value={checkInFilters.item_sku}
                  onChange={(e) => handleFilterChange('check-ins', 'item_sku', e.target.value)}
                  placeholder="Filter by SKU"
                />
              </div>
              <div className="filter-group">
                <label>PO Number</label>
                <input
                  type="text"
                  value={checkInFilters.po_number}
                  onChange={(e) => handleFilterChange('check-ins', 'po_number', e.target.value)}
                  placeholder="Filter by PO number"
                />
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={checkInFilters.date_from}
                  onChange={(e) => handleFilterChange('check-ins', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={checkInFilters.date_to}
                  onChange={(e) => handleFilterChange('check-ins', 'date_to', e.target.value)}
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
                  <th>Checked In At</th>
                  <th>Lot Number</th>
                  <th>Expiration (at check-in)</th>
                  <th>Mfg (at check-in)</th>
                  <th>Vendor Lot #</th>
                  <th>SKU</th>
                  <th>Item Name</th>
                  <th>PO Number</th>
                  <th>Vendor</th>
                  <th>Quantity ({unitDisplay})</th>
                  <th>Status</th>
                  <th>Carrier</th>
                  <th>COA</th>
                  <th>Prod Free Pests</th>
                  <th>Carrier Free Pests</th>
                  <th>Shipment Accepted</th>
                  <th>Initials</th>
                  <th>Short Reason</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {checkInLogs.length === 0 ? (
                  <tr>
                    <td colSpan={19} className="no-data">No check-in logs found</td>
                  </tr>
                ) : (
                  checkInLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.checked_in_at)}</td>
                      <td><strong>{log.lot_number}</strong></td>
                      <td>
                        {log.expiration_date
                          ? formatAppDate(log.expiration_date)
                          : '-'}
                      </td>
                      <td>
                        {log.manufacture_date
                          ? formatAppDate(log.manufacture_date)
                          : '-'}
                      </td>
                      <td>{log.vendor_lot_number || '-'}</td>
                      <td>{log.item_sku}</td>
                      <td>{log.item_name}</td>
                      <td>{log.po_number || '-'}</td>
                      <td>{log.vendor_name || '-'}</td>
                      <td>{formatNumber(convertQuantity(log.quantity, log.quantity_unit, unitDisplay))} {unitDisplay}</td>
                      <td>
                        <span className={`method-badge ${getMethodBadgeClass(log.status)}`}>
                          {log.status}
                        </span>
                      </td>
                      <td>{log.carrier || '-'}</td>
                      <td>{log.coa ? 'Yes' : 'No'}</td>
                      <td>{log.prod_free_pests ? 'Yes' : 'No'}</td>
                      <td>{log.carrier_free_pests ? 'Yes' : 'No'}</td>
                      <td>{log.shipment_accepted ? 'Yes' : 'No'}</td>
                      <td>{log.initials || '-'}</td>
                      <td>{log.short_reason || '-'}</td>
                      <td className="notes-cell">{log.notes || '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {activeLogType === 'lot-attribute-changes' && (
        <>
          <div className="filters-section">
            <div className="filters-grid">
              <div className="filter-group">
                <label>Lot number</label>
                <input
                  type="text"
                  value={lotAttributeFilters.lot_number}
                  onChange={(e) => handleFilterChange('lot-attribute-changes', 'lot_number', e.target.value)}
                  placeholder="Filter by internal lot #"
                />
              </div>
              <div className="filter-group">
                <label>SKU</label>
                <input
                  type="text"
                  value={lotAttributeFilters.sku}
                  onChange={(e) => handleFilterChange('lot-attribute-changes', 'sku', e.target.value)}
                  placeholder="Filter by item SKU"
                />
              </div>
              <div className="filter-group">
                <label>Field</label>
                <input
                  type="text"
                  value={lotAttributeFilters.field_name}
                  onChange={(e) => handleFilterChange('lot-attribute-changes', 'field_name', e.target.value)}
                  placeholder="e.g. expiration_date"
                />
              </div>
              <div className="filter-group">
                <label>Date From</label>
                <input
                  type="datetime-local"
                  value={lotAttributeFilters.date_from}
                  onChange={(e) => handleFilterChange('lot-attribute-changes', 'date_from', e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>Date To</label>
                <input
                  type="datetime-local"
                  value={lotAttributeFilters.date_to}
                  onChange={(e) => handleFilterChange('lot-attribute-changes', 'date_to', e.target.value)}
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
                  <th>Changed At</th>
                  <th>Lot #</th>
                  <th>SKU</th>
                  <th>Field</th>
                  <th>Previous value</th>
                  <th>New value</th>
                  <th>Reason</th>
                  <th>Changed by</th>
                </tr>
              </thead>
              <tbody>
                {lotAttributeChangeLogs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="no-data">No lot field change logs found</td>
                  </tr>
                ) : (
                  lotAttributeChangeLogs.map((log) => (
                    <tr key={log.id}>
                      <td>{formatDate(log.changed_at)}</td>
                      <td><strong>{log.lot_number || '-'}</strong></td>
                      <td>{log.item_sku || '-'}</td>
                      <td><code>{log.field_name}</code></td>
                      <td>{log.old_value || '—'}</td>
                      <td>{log.new_value || '—'}</td>
                      <td className="notes-cell">{log.reason || '—'}</td>
                      <td>{log.changed_by || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="logs-summary">
        <p>Total {
          activeLogType === 'depletion' ? 'depletion' : 
          activeLogType === 'purchase-orders' ? 'purchase order' : 
          activeLogType === 'production' ? 'production' :
          activeLogType === 'check-ins' ? 'check-in' :
          activeLogType === 'lot-attribute-changes' ? 'lot field change' :
          'transaction'
        } logs: <strong>
          {activeLogType === 'depletion' ? depletionLogs.length : 
           activeLogType === 'purchase-orders' ? poLogs.length : 
           activeLogType === 'production' ? productionLogs.length :
           activeLogType === 'check-ins' ? checkInLogs.length :
           activeLogType === 'lot-attribute-changes' ? lotAttributeChangeLogs.length :
           transactionLogs.length}
        </strong></p>
      </div>
    </div>
  )
}

export default Logs
