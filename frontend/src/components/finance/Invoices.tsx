import { useState, useEffect } from 'react'
import { getInvoices, updateInvoice, getAgingReport } from '../../api/invoices'
import { formatCurrency } from '../../utils/formatNumber'
import { formatAppDate } from '../../utils/appDateFormat'
import CreateInvoice from './CreateInvoice'
import ViewInvoice from './ViewInvoice'
import './Invoices.css'

const API_BASE_URL = 'http://localhost:8000/api'

interface Invoice {
  id: number
  invoice_number: string
  sales_order?: {
    id: number
    so_number: string
    customer_name: string
    tracking_number?: string
    customer?: {
      payment_terms?: string
    }
  }
  customer_name?: string
  payment_terms?: string
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

interface InvoicesProps {
  onNavigateToTab?: (tab: string) => void
}

function Invoices({ onNavigateToTab }: InvoicesProps) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showAgingReport, setShowAgingReport] = useState(false)
  const [agingReport, setAgingReport] = useState<any>(null)
  const [editingStatus, setEditingStatus] = useState<number | null>(null)
  const [newStatus, setNewStatus] = useState<string>('')
  const [viewingInvoice, setViewingInvoice] = useState<number | null>(null)
  type InvoiceSortKey = 'invoice_number' | 'customer' | 'invoice_date' | 'due_date' | 'grand_total' | 'status' | null
  const [sort, setSort] = useState<{ key: InvoiceSortKey; dir: 'asc' | 'desc' }>({ key: 'invoice_date', dir: 'desc' })

  const statusLabel = (status: string) => status === 'sent' ? 'Issued' : status

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
      
      // Ensure data is an array
      const invoiceArray = Array.isArray(data) ? data : (data?.results || [])
      
      setInvoices(invoiceArray)
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

  const sortedInvoices = [...invoices].sort((a: Invoice, b: Invoice) => {
    if (!sort.key) {
      if (a.status === 'draft' && b.status !== 'draft') return -1
      if (a.status !== 'draft' && b.status === 'draft') return 1
      return new Date(b.invoice_date).getTime() - new Date(a.invoice_date).getTime()
    }
    let cmp = 0
    switch (sort.key) {
      case 'invoice_number': cmp = (a.invoice_number || '').localeCompare(b.invoice_number || ''); break
      case 'customer': cmp = (a.customer_name || a.sales_order?.customer_name || '').localeCompare(b.customer_name || b.sales_order?.customer_name || ''); break
      case 'invoice_date': cmp = new Date(a.invoice_date).getTime() - new Date(b.invoice_date).getTime(); break
      case 'due_date': cmp = new Date(a.due_date).getTime() - new Date(b.due_date).getTime(); break
      case 'grand_total': cmp = (a.grand_total ?? 0) - (b.grand_total ?? 0); break
      case 'status': cmp = (a.status || '').localeCompare(b.status || ''); break
      default: return 0
    }
    return sort.dir === 'asc' ? cmp : -cmp
  })

  const handleSort = (key: NonNullable<InvoiceSortKey>) => {
    setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
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
        <div className="invoices-header-main">
          <h2>Invoices</h2>
          {onNavigateToTab && (
            <div className="invoices-related-links">
              <span className="related-label">Related:</span>
              <button type="button" className="link-btn" onClick={() => onNavigateToTab('ar')}>Accounts Receivable</button>
              <span className="related-sep">|</span>
              <button type="button" className="link-btn" onClick={() => onNavigateToTab('reports')}>Financial Reports</button>
            </div>
          )}
        </div>
        <div className="header-actions">
          <button
            onClick={() => setShowAgingReport(!showAgingReport)}
            className="btn btn-secondary"
          >
            {showAgingReport ? 'Hide' : 'Show'} Aging Report
          </button>
          <button 
            onClick={() => setShowCreate(true)} 
            className="btn btn-primary"
            title="Create a manual invoice not tied to a sales order"
          >
            + Create Manual Invoice
          </button>
          {invoices.filter((inv: Invoice) => inv.status === 'draft').length > 0 && (
            <span className="draft-count-badge">
              {invoices.filter((inv: Invoice) => inv.status === 'draft').length} Draft{invoices.filter((inv: Invoice) => inv.status === 'draft').length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {showAgingReport && agingReport && (
        <div className="aging-report">
          <h3>Aging Report</h3>
          <div className="aging-buckets">
            <div className="aging-bucket">
              <h4>Current (Not Due)</h4>
              <div className="bucket-total">{formatCurrency(agingReport.buckets.current.total)}</div>
              <div className="bucket-count">{agingReport.buckets.current.invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>0-30 Days</h4>
              <div className="bucket-total">{formatCurrency(agingReport.buckets['0_30'].total)}</div>
              <div className="bucket-count">{agingReport.buckets['0_30'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>31-60 Days</h4>
              <div className="bucket-total">{formatCurrency(agingReport.buckets['31_60'].total)}</div>
              <div className="bucket-count">{agingReport.buckets['31_60'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>61-90 Days</h4>
              <div className="bucket-total">{formatCurrency(agingReport.buckets['61_90'].total)}</div>
              <div className="bucket-count">{agingReport.buckets['61_90'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket">
              <h4>90+ Days</h4>
              <div className="bucket-total">{formatCurrency(agingReport.buckets['90_plus'].total)}</div>
              <div className="bucket-count">{agingReport.buckets['90_plus'].invoices.length} invoices</div>
            </div>
            <div className="aging-bucket grand-total">
              <h4>Grand Total</h4>
              <div className="bucket-total">{formatCurrency(agingReport.grand_total)}</div>
            </div>
          </div>
        </div>
      )}

      <div className="invoices-filters">
        <label className="invoices-filter-label">
          <span className="invoices-filter-text">Status</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="sent">Issued</option>
            <option value="paid">Paid</option>
            <option value="overdue">Overdue</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
      </div>

      <div className="invoices-table-container table-wrapper">
        <table className="invoices-table">
          <thead>
            <tr>
              <th className="sortable sortable-header" onClick={() => handleSort('invoice_number')}>Invoice # {sort.key === 'invoice_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>S.O.</th>
              <th className="sortable sortable-header" onClick={() => handleSort('customer')}>Customer {sort.key === 'customer' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>Tracking</th>
              <th className="sortable sortable-header" onClick={() => handleSort('invoice_date')}>Invoice date {sort.key === 'invoice_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('due_date')}>Due date {sort.key === 'due_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>Terms</th>
              <th>Aging</th>
              <th className="sortable sortable-header inv-col-amount" onClick={() => handleSort('grand_total')}>Total {sort.key === 'grand_total' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable sortable-header" onClick={() => handleSort('status')}>Status {sort.key === 'status' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
            </tr>
          </thead>
          <tbody>
            {sortedInvoices.length === 0 ? (
              <tr>
                <td colSpan={10} className="empty-state">
                  No invoices found.
                </td>
              </tr>
            ) : (
              sortedInvoices.map((invoice) => (
                <tr 
                  key={invoice.id}
                  className={invoice.status === 'draft' ? 'draft-invoice' : ''}
                >
                  <td className="invoice-number">
                    <a
                      href={`${API_BASE_URL}/invoices/${invoice.id}/pdf/`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="invoice-pdf-link"
                      onClick={(e) => {
                        e.preventDefault()
                        window.open(`${API_BASE_URL}/invoices/${invoice.id}/pdf/`, '_blank')
                      }}
                      title="View invoice PDF"
                    >
                      {invoice.invoice_number}
                    </a>
                  </td>
                  <td>
                    {invoice.sales_order?.so_number || '-'}
                  </td>
                  <td>
                    {invoice.customer_name || invoice.sales_order?.customer_name || '-'}
                  </td>
                  <td>
                    {invoice.sales_order?.tracking_number || '-'}
                  </td>
                  <td>{invoice.invoice_date ? formatAppDate(invoice.invoice_date) : '-'}</td>
                  <td>{invoice.due_date ? formatAppDate(invoice.due_date) : '-'}</td>
                  <td>
                    {invoice.payment_terms || invoice.sales_order?.customer?.payment_terms || '-'}
                  </td>
                  <td>
                    <span className={`aging-badge ${getAgingColor(invoice.days_aging)}`}>
                      {getAgingLabel(invoice.days_aging)}
                    </span>
                  </td>
                  <td className="amount">{formatCurrency(invoice.grand_total)}</td>
                  <td className="inv-status-cell">
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
                        <option value="sent">Issued</option>
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
                        title={invoice.status === 'draft' ? 'Click to change status (e.g., to Issued)' : 'Click to change status'}
                      >
                        {statusLabel(invoice.status)}
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

      {viewingInvoice && (
        <ViewInvoice
          invoiceId={viewingInvoice}
          onClose={() => setViewingInvoice(null)}
          onSuccess={() => {
            setViewingInvoice(null)
            setRefreshKey(prev => prev + 1)
          }}
        />
      )}
    </div>
  )
}

export default Invoices






