import React, { useState, useEffect } from 'react'
import { getLotDepletionLogs, LotDepletionLog } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import './LotDepletionLogs.css'

function LotDepletionLogs() {
  const [logs, setLogs] = useState<LotDepletionLog[]>([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    lot_number: '',
    sku: '',
    method: '',
    date_from: '',
    date_to: ''
  })

  useEffect(() => {
    loadLogs()
  }, [])

  const loadLogs = async () => {
    try {
      setLoading(true)
      const activeFilters: any = {}
      if (filters.lot_number) activeFilters.lot_number = filters.lot_number
      if (filters.sku) activeFilters.sku = filters.sku
      if (filters.method) activeFilters.method = filters.method
      if (filters.date_from) activeFilters.date_from = filters.date_from
      if (filters.date_to) activeFilters.date_to = filters.date_to
      
      const data = await getLotDepletionLogs(Object.keys(activeFilters).length > 0 ? activeFilters : undefined)
      setLogs(Array.isArray(data) ? data : [])
    } catch (error: any) {
      console.error('Failed to load depletion logs:', error)
      alert(`Failed to load depletion logs: ${error.message || 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (field: string, value: string) => {
    setFilters(prev => ({ ...prev, [field]: value }))
  }

  const handleApplyFilters = () => {
    loadLogs()
  }

  const handleClearFilters = () => {
    setFilters({
      lot_number: '',
      sku: '',
      method: '',
      date_from: '',
      date_to: ''
    })
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
      'reversal': 'badge-reversal'
    }
    return classes[method] || 'badge-default'
  }

  if (loading) {
    return (
      <div className="depletion-logs-container">
        <div className="loading">Loading depletion logs...</div>
      </div>
    )
  }

  return (
    <div className="depletion-logs-container">
      <div className="depletion-logs-header">
        <h2>Lot Depletion Logs</h2>
        <p className="subtitle">Track when lots are depleted to zero or below</p>
      </div>

      <div className="filters-section">
        <div className="filters-grid">
          <div className="filter-group">
            <label>Lot Number</label>
            <input
              type="text"
              value={filters.lot_number}
              onChange={(e) => handleFilterChange('lot_number', e.target.value)}
              placeholder="Filter by lot number"
            />
          </div>
          <div className="filter-group">
            <label>SKU</label>
            <input
              type="text"
              value={filters.sku}
              onChange={(e) => handleFilterChange('sku', e.target.value)}
              placeholder="Filter by SKU"
            />
          </div>
          <div className="filter-group">
            <label>Depletion Method</label>
            <select
              value={filters.method}
              onChange={(e) => handleFilterChange('method', e.target.value)}
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
              value={filters.date_from}
              onChange={(e) => handleFilterChange('date_from', e.target.value)}
            />
          </div>
          <div className="filter-group">
            <label>Date To</label>
            <input
              type="datetime-local"
              value={filters.date_to}
              onChange={(e) => handleFilterChange('date_to', e.target.value)}
            />
          </div>
        </div>
        <div className="filter-actions">
          <button onClick={handleApplyFilters} className="btn-apply">Apply Filters</button>
          <button onClick={handleClearFilters} className="btn-clear">Clear Filters</button>
        </div>
      </div>

      <div className="logs-table-wrapper">
        <table className="depletion-logs-table">
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
            {logs.length === 0 ? (
              <tr>
                <td colSpan={12} className="no-data">No depletion logs found</td>
              </tr>
            ) : (
              logs.map((log) => (
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

      {logs.length > 0 && (
        <div className="logs-summary">
          <p>Total logs: <strong>{logs.length}</strong></p>
        </div>
      )}
    </div>
  )
}

export default LotDepletionLogs
