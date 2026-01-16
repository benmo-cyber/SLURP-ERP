import { useState, useEffect } from 'react'
import { getInvoice, updateInvoice } from '../../api/invoices'
import { formatCurrency } from '../../utils/formatNumber'
import './ViewInvoice.css'

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
  invoice_date: string
  due_date: string
  status: string
  subtotal: number
  freight: number
  tax: number
  discount: number
  grand_total: number
  notes?: string
  items?: Array<{
    id: number
    item?: {
      id: number
      sku: string
      name: string
    }
    description: string
    quantity: number
    unit_price: number
    line_total: number
  }>
}

interface ViewInvoiceProps {
  invoiceId: number
  onClose: () => void
  onSuccess: () => void
}

function ViewInvoice({ invoiceId, onClose, onSuccess }: ViewInvoiceProps) {
  const [invoice, setInvoice] = useState<Invoice | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({
    status: '',
    tracking_number: '',
    notes: '',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadInvoice()
  }, [invoiceId])

  const loadInvoice = async () => {
    try {
      setLoading(true)
      const data = await getInvoice(invoiceId)
      setInvoice(data)
      setFormData({
        status: data.status,
        tracking_number: data.sales_order?.tracking_number || '',
        notes: data.notes || '',
      })
    } catch (error) {
      console.error('Failed to load invoice:', error)
      alert('Failed to load invoice')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!invoice) return

    try {
      setSubmitting(true)
      
      // Update invoice status
      await updateInvoice(invoice.id, {
        status: formData.status,
        notes: formData.notes,
      })

      // Update sales order tracking number if changed
      if (invoice.sales_order && formData.tracking_number !== invoice.sales_order.tracking_number) {
        const { updateSalesOrder } = await import('../../api/salesOrders')
        await updateSalesOrder(invoice.sales_order.id, {
          tracking_number: formData.tracking_number,
        })
      }

      alert('Invoice updated successfully!')
      setEditing(false)
      onSuccess()
      loadInvoice() // Reload to get updated data
    } catch (error: any) {
      console.error('Failed to update invoice:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to update invoice')
    } finally {
      setSubmitting(false)
    }
  }

  const handlePrintPackingList = async () => {
    if (!invoice?.sales_order?.id) return

    try {
      const url = `http://localhost:8000/api/sales-orders/${invoice.sales_order.id}/packing-list/`
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (error: any) {
      console.error('Failed to open packing list:', error)
      alert('Failed to open packing list')
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content view-invoice-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Invoice Details</h2>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
          <div className="modal-body">
            <div className="loading">Loading invoice...</div>
          </div>
        </div>
      </div>
    )
  }

  if (!invoice) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content view-invoice-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Invoice Details</h2>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
          <div className="modal-body">
            <div className="error">Invoice not found</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content view-invoice-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Invoice {invoice.invoice_number}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="modal-body">
          <div className="invoice-details">
            <div className="detail-section">
              <h3>Invoice Information</h3>
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Invoice Number:</label>
                  <span>{invoice.invoice_number}</span>
                </div>
                <div className="detail-item">
                  <label>Status:</label>
                  {editing ? (
                    <select
                      value={formData.status}
                      onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                      className="status-select"
                    >
                      <option value="draft">Draft</option>
                      <option value="sent">Sent</option>
                      <option value="paid">Paid</option>
                      <option value="overdue">Overdue</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  ) : (
                    <span className={`status-badge status-${invoice.status}`}>{invoice.status}</span>
                  )}
                </div>
                <div className="detail-item">
                  <label>Invoice Date:</label>
                  <span>{new Date(invoice.invoice_date).toLocaleDateString()}</span>
                </div>
                <div className="detail-item">
                  <label>Due Date:</label>
                  <span>{new Date(invoice.due_date).toLocaleDateString()}</span>
                </div>
              </div>
            </div>

            {invoice.sales_order && (
              <div className="detail-section">
                <h3>Sales Order Information</h3>
                <div className="detail-grid">
                  <div className="detail-item">
                    <label>Sales Order:</label>
                    <span>{invoice.sales_order.so_number}</span>
                  </div>
                  <div className="detail-item">
                    <label>Customer:</label>
                    <span>{invoice.sales_order.customer_name}</span>
                  </div>
                  <div className="detail-item">
                    <label>Payment Terms:</label>
                    <span>{invoice.sales_order.customer?.payment_terms || '-'}</span>
                  </div>
                  <div className="detail-item">
                    <label>Tracking Number:</label>
                    {editing ? (
                      <input
                        type="text"
                        value={formData.tracking_number}
                        onChange={(e) => setFormData({ ...formData, tracking_number: e.target.value })}
                        placeholder="Enter tracking number"
                      />
                    ) : (
                      <span>{invoice.sales_order.tracking_number || '-'}</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="detail-section">
              <h3>Invoice Items</h3>
              <table className="items-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Description</th>
                    <th>Quantity</th>
                    <th>Unit Price</th>
                    <th>Line Total</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.items && invoice.items.length > 0 ? (
                    invoice.items.map((item, index) => (
                      <tr key={item.id || index}>
                        <td>{item.item?.sku || '-'}</td>
                        <td>{item.description}</td>
                        <td>{item.quantity}</td>
                        <td>{formatCurrency(item.unit_price)}</td>
                        <td>{formatCurrency(item.line_total)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="empty-state">No items found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="detail-section">
              <h3>Totals</h3>
              <div className="totals-grid">
                <div className="total-row">
                  <label>Subtotal:</label>
                  <span>{formatCurrency(invoice.subtotal)}</span>
                </div>
                <div className="total-row">
                  <label>Freight:</label>
                  <span>{formatCurrency(invoice.freight)}</span>
                </div>
                <div className="total-row">
                  <label>Tax:</label>
                  <span>{formatCurrency(invoice.tax)}</span>
                </div>
                <div className="total-row">
                  <label>Discount:</label>
                  <span>{formatCurrency(invoice.discount)}</span>
                </div>
                <div className="total-row total-final">
                  <label>Grand Total:</label>
                  <span>{formatCurrency(invoice.grand_total)}</span>
                </div>
              </div>
            </div>

            <div className="detail-section">
              <h3>Notes</h3>
              {editing ? (
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  rows={4}
                  placeholder="Add notes..."
                />
              ) : (
                <div className="notes-display">{invoice.notes || 'No notes'}</div>
              )}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <div className="footer-actions">
            {invoice.sales_order && (
              <button
                onClick={handlePrintPackingList}
                className="btn btn-secondary"
                title="View Packing List"
              >
                📦 Packing List
              </button>
            )}
          </div>
          <div className="footer-actions">
            {editing ? (
              <>
                <button
                  onClick={() => {
                    setEditing(false)
                    loadInvoice() // Reload to reset form
                  }}
                  className="btn btn-secondary"
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  className="btn btn-primary"
                  disabled={submitting}
                >
                  {submitting ? 'Saving...' : 'Save Changes'}
                </button>
              </>
            ) : (
              <>
                <button onClick={onClose} className="btn btn-secondary">
                  Close
                </button>
                <button onClick={() => setEditing(true)} className="btn btn-primary">
                  Edit Invoice
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default ViewInvoice
