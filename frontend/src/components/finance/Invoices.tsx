import { useState, useEffect } from 'react'
import { getInvoices, updateInvoice, getAgingReport } from '../../api/invoices'
import CreateInvoice from './CreateInvoice'
import './Invoices.css'

interface Invoice {
  id: number
  invoice_number: string
  sales_order: {
    id: number
    so_number: string
    customer_name: string
    customer?: {
      payment_terms?: string
    }
  }
  invoice_date: string
  due_date: string
  status: string
  subtotal: number
  freight: number
  tax: number
  discount: number
  grand_total: number
  days_aging: number
}

function Invoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showAgingReport, setShowAgingReport] = useState(false)
  const [agingReport, setAgingReport] = useState<any>(null)
  const [editingStatus, setEditingStatus] = useState<number | null>(null)
  const [newStatus, setNewStatus] = useState<string>('')

  useEffect(() => {
    loadInvoices()
  }, [refreshKey, statusFilter])

  useEffect(() => {
    if (showAgingReport) {
      loadAgingReport()
    }
  }, [showAgingReport])

  const loadInvoices = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (statusFilter) {
        params.status = statusFilter
      }
      const data = await getInvoices(params)
      setInvoices(data)
    } catch (error) {
      console.error('Failed to load invoices:', error)
      alert('Failed to load invoices')
    } finally {
      setLoading(false)
    }
  }

  const loadAgingReport = async () => {
    try {
      const report = await getAgingReport()
      setAgingReport(report)
    } catch (error) {
      console.error('Failed to load aging report:', error)
      alert('Failed to load aging report')
    }
  }

  const handleStatusChange = async (invoiceId: number, status: string) => {
    try {
      await updateInvoice(invoiceId, { status })
      setRefreshKey(prev => prev + 1)
      setEditingStatus(null)
    } catch (error) {
      console.error('Failed to update invoice status:', error)
      alert('Failed to update invoice status')
    }
  }

  const getAgingColor = (days: number): string => {
    if (days < 0) return 'aging-current' // Not yet due
    if (days <= 30) return 'aging-0-30'
    if (days <= 60) return 'aging-31-60'
    if (days <= 90) return 'aging-61-90'
    return 'aging-90-plus'
  }

  const getAgingLabel = (days: number): string => {
    if (days < 0) return 'Current'
    if (days <= 30) return `${days} days`
    if (days <= 60) return `${days} days`
    if (days <= 90) return `${days} days`
    return `${days}+ days`
  }

  const handleCreateSuccess = () => {
    setShowCreate(false)
    setRefreshKey(prev => prev + 1)
  }

  if (loading) {
    return <div className="loading">Loading invoices...</div>
  }

  return (
    <div className="invoices">
      <div className="invoices-header">
        <h2>Invoices</h2>
        <div className="header-actions">
          <button
            onClick={() => setShowAgingReport(!showAgingReport)}
            className="btn btn-secondary"
          >
            {showAgingReport ? 'Hide' : 'Show'} Aging Report
          </button>
          <button onClick={() => setShowCreate(true)} className="btn btn-primary">
            + Create Invoice
          </button>
        </div>
      </div>

      {showAgingReport && agingReport && (
        <div className="aging-report">
          <h3>Aging Report</h3>
          <div className="aging-buckets">
            <div className="aging-bucket">
              <h4>Current (Not Due)</h4>
              <div className="bucket-total">${agingReport.buckets.current.total.toFixed(2)}</div>
              <div className="bucket-count">{agingReport.buckets.current.invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>0-30 Days</h4>
              <div className="bucket-total">${agingReport.buckets['0_30'].total.toFixed(2)}</div>
              <div className="bucket-count">{agingReport.buckets['0_30'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>31-60 Days</h4>
              <div className="bucket-total">${agingReport.buckets['31_60'].total.toFixed(2)}</div>
              <div className="bucket-count">{agingReport.buckets['31_60'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>61-90 Days</h4>
              <div className="bucket-total">${agingReport.buckets['61_90'].total.toFixed(2)}</div>
              <div className="bucket-count">{agingReport.buckets['61_90'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>90+ Days</h4>
              <div className="bucket-total">${agingReport.buckets['90_plus'].total.toFixed(2)}</div>
              <div className="bucket-count">{agingReport.buckets['90_plus'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket grand-total">
              <h4>Grand Total</h4>
              <div className="bucket-total">${agingReport.grand_total.toFixed(2)}</div>
            </div>
          </div>
        </div>
      )}

      <div className="filters">
        <label>
          Filter by Status:
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="paid">Paid</option>
            <option value="overdue">Overdue</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
      </div>

      <div className="invoices-table-container">
        <table className="invoices-table">
          <thead>
            <tr>
              <th>Invoice Number</th>
              <th>Sales Order</th>
              <th>Customer</th>
              <th>Invoice Date</th>
              <th>Due Date</th>
              <th>Payment Terms</th>
              <th>Days Aging</th>
              <th>Grand Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 ? (
              <tr>
                <td colSpan={9} className="empty-state">
                  No invoices found.
                </td>
              </tr>
            ) : (
              invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="invoice-number">{invoice.invoice_number}</td>
                  <td>{invoice.sales_order?.so_number || '-'}</td>
                  <td>{invoice.sales_order?.customer_name || '-'}</td>
                  <td>{new Date(invoice.invoice_date).toLocaleDateString()}</td>
                  <td>{new Date(invoice.due_date).toLocaleDateString()}</td>
                  <td>{invoice.sales_order?.customer?.payment_terms || '-'}</td>
                  <td>
                    <span className={`aging-badge ${getAgingColor(invoice.days_aging)}`}>
                      {getAgingLabel(invoice.days_aging)}
                    </span>
                  </td>
                  <td className="amount">${invoice.grand_total.toFixed(2)}</td>
                  <td>
                    {editingStatus === invoice.id ? (
                      <select
                        value={newStatus}
                        onChange={(e) => setNewStatus(e.target.value)}
                        onBlur={() => {
                          if (newStatus) {
                            handleStatusChange(invoice.id, newStatus)
                          } else {
                            setEditingStatus(null)
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && newStatus) {
                            handleStatusChange(invoice.id, newStatus)
                          } else if (e.key === 'Escape') {
                            setEditingStatus(null)
                          }
                        }}
                        autoFocus
                        className="status-select"
                      >
                        <option value="draft">Draft</option>
                        <option value="sent">Sent</option>
                        <option value="paid">Paid</option>
                        <option value="overdue">Overdue</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                    ) : (
                      <span
                        className={`status-badge status-${invoice.status} clickable`}
                        onClick={() => {
                          setEditingStatus(invoice.id)
                          setNewStatus(invoice.status)
                        }}
                      >
                        {invoice.status}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateInvoice
          onClose={() => setShowCreate(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  )
}

export default Invoices






