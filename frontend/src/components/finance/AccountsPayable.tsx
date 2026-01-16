import React, { useState, useEffect } from 'react'
import { getAccountsPayable, getAccountsPayableAging, updateAccountsPayableEntry } from '../../api/finance'
import PaymentEntry from './PaymentEntry'
import './AccountsPayable.css'

interface AccountsPayableEntry {
  id: number
  vendor_name: string
  invoice_number: string
  invoice_date: string
  due_date: string
  original_amount: number
  amount_paid: number
  balance: number
  status: string
  days_aging: number
  aging_bucket: string
  po_number?: string
  purchase_order?: number
}

const AccountsPayable: React.FC = () => {
  const [entries, setEntries] = useState<AccountsPayableEntry[]>([])
  const [agingReport, setAgingReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [showAging, setShowAging] = useState(false)
  const [showPaymentEntry, setShowPaymentEntry] = useState(false)
  const [selectedApEntryId, setSelectedApEntryId] = useState<number | null>(null)
  const [filters, setFilters] = useState({
    status: '',
    vendor_name: ''
  })

  useEffect(() => {
    loadData()
  }, [filters])

  const loadData = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (filters.status) params.status = filters.status
      if (filters.vendor_name) params.vendor_name = filters.vendor_name

      const data = await getAccountsPayable(params)
      setEntries(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load AP entries:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadAgingReport = async () => {
    try {
      const data = await getAccountsPayableAging()
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

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  return (
    <div className="accounts-payable">
      <div className="ap-header">
        <h2>Accounts Payable</h2>
        <div className="ap-actions">
          <button onClick={loadAgingReport} className="btn btn-secondary">
            View Aging Report
          </button>
          <button onClick={() => {
            setSelectedApEntryId(null)
            setShowPaymentEntry(true)
          }} className="btn btn-primary">
            Record Payment
          </button>
        </div>
      </div>

      <div className="ap-filters">
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
          placeholder="Filter by vendor name..."
          value={filters.vendor_name}
          onChange={(e) => setFilters({ ...filters, vendor_name: e.target.value })}
          className="filter-input"
        />
      </div>

      {showAging && agingReport && (
        <div className="aging-report">
          <div className="aging-header">
            <h3>AP Aging Report - As of {formatDate(agingReport.as_of_date)}</h3>
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
        <div className="ap-table-container">
          <table className="ap-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Invoice #</th>
                <th>PO #</th>
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
                  <td colSpan={11} className="empty-state">No AP entries found</td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.vendor_name}</td>
                    <td>{entry.invoice_number}</td>
                    <td>{entry.po_number || '-'}</td>
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
                            setSelectedApEntryId(entry.id)
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
            setSelectedApEntryId(null)
          }}
          onSuccess={() => {
            loadData()
            setShowPaymentEntry(false)
            setSelectedApEntryId(null)
          }}
          paymentType="ap_payment"
          apEntryId={selectedApEntryId || undefined}
        />
      )}
    </div>
  )
}

export default AccountsPayable
