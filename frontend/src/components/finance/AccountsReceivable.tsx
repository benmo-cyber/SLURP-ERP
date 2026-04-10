import React, { useState, useEffect } from 'react'
import { getAccountsReceivable, getAccountsReceivableAging, updateAccountsReceivableEntry } from '../../api/finance'
import PaymentEntry from './PaymentEntry'
import { formatAppDate } from '../../utils/appDateFormat'
import './AccountsReceivable.css'

interface AccountsReceivableEntry {
  id: number
  customer_name: string
  invoice_number_display: string
  invoice_date: string
  due_date: string
  original_amount: number
  amount_paid: number
  balance: number
  status: string
  days_aging: number
  aging_bucket: string
  so_number?: string
  sales_order?: number
}

interface AccountsReceivableProps {
  onNavigateToTab?: (tab: string) => void
}

const AccountsReceivable: React.FC<AccountsReceivableProps> = ({ onNavigateToTab }) => {
  const [entries, setEntries] = useState<AccountsReceivableEntry[]>([])
  const [agingReport, setAgingReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [showAging, setShowAging] = useState(false)
  const [showPaymentEntry, setShowPaymentEntry] = useState(false)
  const [selectedArEntryId, setSelectedArEntryId] = useState<number | null>(null)
  const [filters, setFilters] = useState({
    status: '',
    customer_name: ''
  })

  useEffect(() => {
    loadData()
  }, [filters])

  const loadData = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (filters.status) params.status = filters.status
      if (filters.customer_name) params.customer_name = filters.customer_name

      const data = await getAccountsReceivable(params)
      setEntries(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load AR entries:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadAgingReport = async () => {
    try {
      const data = await getAccountsReceivableAging()
      setAgingReport(data)
      setShowAging(true)
    } catch (error) {
      console.error('Failed to load aging report:', error)
    }
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'paid': return 'status-paid'
      case 'partial': return 'status-partial'
      case 'overdue': return 'status-overdue'
      case 'open': return 'status-open'
      default: return 'status-default'
    }
  }

  const getAgingBucketClass = (bucket: string) => {
    switch (bucket) {
      case 'over_90': return 'aging-over-90'
      case '61-90': return 'aging-61-90'
      case '31-60': return 'aging-31-60'
      case '0-30': return 'aging-0-30'
      default: return 'aging-not-due'
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
  }

  const formatDate = (dateString: string) => formatAppDate(dateString)

  return (
    <div className="accounts-receivable">
      <div className="ar-header">
        <h2>Accounts Receivable</h2>
        {onNavigateToTab && (
          <div className="ar-related-links">
            <span className="related-label">Related:</span>
            <button type="button" className="link-btn" onClick={() => onNavigateToTab('invoices')}>Invoices</button>
            <span className="related-sep">|</span>
            <button type="button" className="link-btn" onClick={() => onNavigateToTab('reports')}>Financial Reports</button>
          </div>
        )}
        <div className="ar-actions">
          <button onClick={loadAgingReport} className="btn btn-secondary">
            View Aging Report
          </button>
          <button onClick={() => {
            setSelectedArEntryId(null)
            setShowPaymentEntry(true)
          }} className="btn btn-primary">
            Record Payment
          </button>
        </div>
      </div>

      <div className="ar-filters">
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="filter-select"
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="partial">Partial</option>
          <option value="paid">Paid</option>
          <option value="overdue">Overdue</option>
        </select>
        <input
          type="text"
          placeholder="Filter by customer name..."
          value={filters.customer_name}
          onChange={(e) => setFilters({ ...filters, customer_name: e.target.value })}
          className="filter-input"
        />
      </div>

      {showAging && agingReport && (
        <div className="aging-report">
          <div className="aging-header">
            <h3>AR Aging Report - As of {formatDate(agingReport.as_of_date)}</h3>
            <button onClick={() => setShowAging(false)} className="btn-close">×</button>
          </div>
          <div className="aging-buckets">
            {Object.entries(agingReport.aging_data).map(([bucket, entries]: [string, any]) => (
              <div key={bucket} className={`aging-bucket ${getAgingBucketClass(bucket)}`}>
                <h4>{bucket === 'not_due' ? 'Not Due' : bucket === 'over_90' ? 'Over 90 Days' : `${bucket} Days`}</h4>
                <div className="bucket-total">{formatCurrency(agingReport.totals[bucket])}</div>
                <div className="bucket-count">{entries.length} entries</div>
              </div>
            ))}
          </div>
          <div className="aging-total">
            <strong>Total Outstanding: {formatCurrency(agingReport.totals.total)}</strong>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <div className="ar-table-container">
          <table className="ar-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Invoice #</th>
                <th>SO #</th>
                <th>Invoice Date</th>
                <th>Due Date</th>
                <th>Original Amount</th>
                <th>Amount Paid</th>
                <th>Balance</th>
                <th>Status</th>
                <th>Days Aging</th>
                <th>Aging Bucket</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={11} className="empty-state">No AR entries found</td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.customer_name}</td>
                    <td>{entry.invoice_number_display || '-'}</td>
                    <td>{entry.so_number || '-'}</td>
                    <td>{formatDate(entry.invoice_date)}</td>
                    <td>{formatDate(entry.due_date)}</td>
                    <td className="amount">{formatCurrency(entry.original_amount)}</td>
                    <td className="amount">{formatCurrency(entry.amount_paid)}</td>
                    <td className="amount balance">{formatCurrency(entry.balance)}</td>
                    <td>
                      <span className={`status-badge ${getStatusBadgeClass(entry.status)}`}>
                        {entry.status}
                      </span>
                    </td>
                    <td>{entry.days_aging}</td>
                    <td>
                      <span className={`aging-badge ${getAgingBucketClass(entry.aging_bucket)}`}>
                        {entry.aging_bucket === 'not_due' ? 'Not Due' : entry.aging_bucket === 'over_90' ? 'Over 90' : entry.aging_bucket}
                      </span>
                    </td>
                    <td>
                      {entry.balance > 0 && (
                        <button
                          onClick={() => {
                            setSelectedArEntryId(entry.id)
                            setShowPaymentEntry(true)
                          }}
                          className="btn-pay"
                          title="Record Payment"
                        >
                          Pay
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr className="totals-row">
                <td colSpan={5}><strong>Totals:</strong></td>
                <td className="amount"><strong>{formatCurrency(entries.reduce((sum, e) => sum + e.original_amount, 0))}</strong></td>
                <td className="amount"><strong>{formatCurrency(entries.reduce((sum, e) => sum + e.amount_paid, 0))}</strong></td>
                <td className="amount balance"><strong>{formatCurrency(entries.reduce((sum, e) => sum + e.balance, 0))}</strong></td>
                <td colSpan={3}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {showPaymentEntry && (
        <PaymentEntry
          onClose={() => {
            setShowPaymentEntry(false)
            setSelectedArEntryId(null)
          }}
          onSuccess={() => {
            loadData()
            setShowPaymentEntry(false)
            setSelectedArEntryId(null)
          }}
          paymentType="ar_payment"
          arEntryId={selectedArEntryId || undefined}
        />
      )}
    </div>
  )
}

export default AccountsReceivable
