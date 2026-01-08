import { useState, useEffect } from 'react'
import { getInvoices } from '../../api/finance'
import CreateInvoice from './CreateInvoice'
import './Invoices.css'

function Invoices() {
  const [invoices, setInvoices] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    loadInvoices()
  }, [refreshKey])

  const loadInvoices = async () => {
    try {
      setLoading(true)
      const data = await getInvoices()
      setInvoices(data)
    } catch (error) {
      console.error('Failed to load invoices:', error)
      alert('Failed to load invoices')
    } finally {
      setLoading(false)
    }
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
        <button onClick={() => setShowCreate(true)} className="btn btn-primary">
          + Create Invoice
        </button>
      </div>

      <div className="invoices-table-container">
        <table className="invoices-table">
          <thead>
            <tr>
              <th>Invoice Number</th>
              <th>Type</th>
              <th>Customer/Vendor</th>
              <th>Invoice Date</th>
              <th>Due Date</th>
              <th>Total Amount</th>
              <th>Paid Amount</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  No invoices found. Click "Create Invoice" to add one.
                </td>
              </tr>
            ) : (
              invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="invoice-number">{invoice.invoice_number}</td>
                  <td>
                    <span className="badge badge-type">{invoice.invoice_type}</span>
                  </td>
                  <td>{invoice.customer_vendor_name}</td>
                  <td>{new Date(invoice.invoice_date).toLocaleDateString()}</td>
                  <td>{invoice.due_date ? new Date(invoice.due_date).toLocaleDateString() : '-'}</td>
                  <td className="amount">${invoice.total_amount.toFixed(2)}</td>
                  <td className="amount">${invoice.paid_amount.toFixed(2)}</td>
                  <td>
                    <span className={`status-badge status-${invoice.status}`}>
                      {invoice.status}
                    </span>
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






