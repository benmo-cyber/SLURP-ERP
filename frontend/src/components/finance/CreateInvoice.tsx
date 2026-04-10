import { useState, useEffect } from 'react'
import { getItems, createInvoice } from '../../api/finance'
import { getSalesOrder } from '../../api/salesOrders'
import { getCustomerContacts } from '../../api/customers'
import { useGodMode } from '../../context/GodModeContext'
import './CreateInvoice.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
  item_type: string
}

interface InvoiceItem {
  item_id: string
  description: string
  quantity: string
  unit_price: string
  line_total: string
}

interface CreateInvoiceProps {
  onClose: () => void
  onSuccess: () => void
  salesOrderId?: number // Optional: if provided, auto-populate from sales order
}

function CreateInvoice({ onClose, onSuccess, salesOrderId }: CreateInvoiceProps) {
  const [items, setItems] = useState<Item[]>([])
  const [formData, setFormData] = useState({
    invoice_number: '', // Leave blank for auto-generation; set for legacy / God mode
    invoice_type: 'customer',
    customer_vendor_name: '',
    customer_vendor_id: '',
    invoice_date: new Date().toISOString().split('T')[0],
    due_date: '',
    tax_amount: '0',
    freight: '0',
    discount: '0',
  })
  const [invoiceItems, setInvoiceItems] = useState<InvoiceItem[]>([
    { item_id: '', description: '', quantity: '', unit_price: '', line_total: '' }
  ])
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(false)
  const [contacts, setContacts] = useState<{ id: number; first_name: string; last_name: string; contact_type?: string }[]>([])
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null)
  const { maxDateForEntry } = useGodMode()

  useEffect(() => {
    loadItems()
    if (salesOrderId) {
      loadSalesOrderData()
    }
  }, [salesOrderId])

  const loadItems = async () => {
    try {
      const data = await getItems()
      // For customer invoices, only show distributed items and finished goods
      if (formData.invoice_type === 'customer') {
        setItems(data.filter((item: Item) => 
          item.item_type === 'distributed_item' || item.item_type === 'finished_good'
        ))
      } else {
        setItems(data)
      }
    } catch (error) {
      console.error('Failed to load items:', error)
    }
  }

  const loadSalesOrderData = async () => {
    if (!salesOrderId) return
    
    try {
      setLoading(true)
      const salesOrder = await getSalesOrder(salesOrderId)
      
      // Load contacts when customer invoice and we have a customer
      if (salesOrder.customer?.id) {
        try {
          const list = await getCustomerContacts(salesOrder.customer.id)
          const arr = Array.isArray(list) ? list : (list?.results ?? [])
          setContacts(arr)
          setSelectedContactId(salesOrder.contact?.id ?? null)
        } catch {
          setContacts([])
          setSelectedContactId(null)
        }
      } else {
        setContacts([])
        setSelectedContactId(null)
      }
      
      // Auto-populate form data from sales order
      setFormData(prev => ({
        ...prev,
        customer_vendor_name: salesOrder.customer_name || '',
        customer_vendor_id: salesOrder.customer_reference_number || '',
        invoice_date: salesOrder.actual_ship_date 
          ? new Date(salesOrder.actual_ship_date).toISOString().split('T')[0]
          : new Date().toISOString().split('T')[0],
      }))
      
      // Auto-populate invoice items from sales order items
      if (salesOrder.items && salesOrder.items.length > 0) {
        const populatedItems = salesOrder.items.map((item: any) => ({
          item_id: item.item?.id?.toString() || '',
          description: item.item?.name || '',
          quantity: item.quantity_shipped?.toString() || item.quantity_ordered?.toString() || '',
          unit_price: item.unit_price?.toString() || '',
          line_total: ((item.quantity_shipped || item.quantity_ordered || 0) * (item.unit_price || 0)).toFixed(2),
        }))
        setInvoiceItems(populatedItems)
      }
    } catch (error) {
      console.error('Failed to load sales order data:', error)
      alert('Failed to load sales order data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [formData.invoice_type])

  const addItem = () => {
    setInvoiceItems([...invoiceItems, { item_id: '', description: '', quantity: '', unit_price: '', line_total: '' }])
  }

  const removeItem = (index: number) => {
    if (invoiceItems.length > 1) {
      setInvoiceItems(invoiceItems.filter((_, i) => i !== index))
    }
  }

  const updateItem = (index: number, field: keyof InvoiceItem, value: string) => {
    const newItems = [...invoiceItems]
    newItems[index] = { ...newItems[index], [field]: value }
    
    // Auto-calculate line total
    if (field === 'quantity' || field === 'unit_price') {
      const qty = parseFloat(newItems[index].quantity || '0')
      const price = parseFloat(newItems[index].unit_price || '0')
      newItems[index].line_total = (qty * price).toFixed(2)
    }
    
    setInvoiceItems(newItems)
  }

  const calculateTotals = () => {
    const subtotal = invoiceItems.reduce((sum, item) => sum + parseFloat(item.line_total || '0'), 0)
    const tax = parseFloat(formData.tax_amount || '0')
    const freight = parseFloat(formData.freight || '0')
    const discount = parseFloat(formData.discount || '0')
    const total = subtotal + tax + freight - discount
    return { subtotal, tax, freight, discount, total }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.customer_vendor_name) {
      alert('Please enter customer/vendor name')
      return
    }

    const validItems = invoiceItems.filter(item => item.item_id && item.quantity && item.unit_price)
    if (validItems.length === 0) {
      alert('Please add at least one invoice item')
      return
    }

    try {
      setSubmitting(true)
      
      const { subtotal, tax, freight, discount, total } = calculateTotals()
      
      const invoiceData: any = {
        invoice_type: formData.invoice_type,
        customer_vendor_name: formData.customer_vendor_name,
        customer_vendor_id: formData.customer_vendor_id || null,
        ...(formData.invoice_number?.trim() && { invoice_number: formData.invoice_number.trim() }),
        invoice_date: formData.invoice_date,
        due_date: formData.due_date || null,
        tax_amount: tax,
        freight: freight,
        discount: discount,
        items: validItems.map(item => ({
          item_id: item.item_id ? parseInt(item.item_id) : null,
          description: item.description || '',
          quantity: parseFloat(item.quantity),
          unit_price: parseFloat(item.unit_price),
          line_total: parseFloat(item.line_total),
        }))
      }
      
      // If salesOrderId is provided, link the invoice to the sales order
      if (salesOrderId) {
        invoiceData.sales_order_id = salesOrderId
      }
      if (formData.invoice_type === 'customer' && selectedContactId) {
        invoiceData.contact = selectedContactId
      }
      
      await createInvoice(invoiceData)
      
      alert(salesOrderId ? 'Invoice updated successfully!' : 'Invoice created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create invoice:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create invoice')
    } finally {
      setSubmitting(false)
    }
  }

  const { subtotal, tax, total } = calculateTotals()

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content invoice-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{salesOrderId ? 'Review & Issue Invoice' : 'Create Manual Invoice'}</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        {loading && (
          <div className="loading-message">Loading sales order data...</div>
        )}

        <form onSubmit={handleSubmit} className="invoice-form">
          <div className="form-row">
            <div className="form-group">
              <label>Invoice Number (leave blank for auto-generation)</label>
              <input
                type="text"
                value={formData.invoice_number}
                onChange={(e) => setFormData({ ...formData, invoice_number: e.target.value })}
                placeholder="e.g. legacy INV-2023-001"
              />
              <small style={{ color: '#666', fontSize: '0.85rem' }}>For legacy or historical data (God mode), enter the number to use.</small>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Invoice Type *</label>
              <select
                value={formData.invoice_type}
                onChange={(e) => setFormData({ ...formData, invoice_type: e.target.value })}
                required
              >
                <option value="customer">Customer Invoice</option>
                <option value="vendor">Vendor Bill</option>
              </select>
            </div>
            <div className="form-group">
              <label>{formData.invoice_type === 'customer' ? 'Customer' : 'Vendor'} Name *</label>
              <input
                type="text"
                value={formData.customer_vendor_name}
                onChange={(e) => setFormData({ ...formData, customer_vendor_name: e.target.value })}
                required
              />
            </div>
            {formData.invoice_type === 'customer' && salesOrderId && contacts.length > 0 && (
              <div className="form-group">
                <label>Contact</label>
                <select
                  value={selectedContactId ?? ''}
                  onChange={(e) => setSelectedContactId(e.target.value ? parseInt(e.target.value) : null)}
                >
                  <option value="">Select Contact (optional)</option>
                  {contacts.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.first_name} {c.last_name}{c.contact_type ? ` (${String(c.contact_type).charAt(0).toUpperCase() + String(c.contact_type).slice(1)})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Invoice Date *</label>
              <input
                type="date"
                value={formData.invoice_date}
                onChange={(e) => setFormData({ ...formData, invoice_date: e.target.value })}
                max={maxDateForEntry}
                required
              />
            </div>
            <div className="form-group">
              <label>Due Date</label>
              <input
                type="date"
                value={formData.due_date}
                onChange={(e) => setFormData({ ...formData, due_date: e.target.value })}
              />
            </div>
          </div>

          <div className="items-section">
            <div className="items-header">
              <h3>Invoice Items</h3>
              <button type="button" onClick={addItem} className="btn btn-secondary btn-sm">
                + Add Item
              </button>
            </div>

            <table className="items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit Price</th>
                  <th>Line Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {invoiceItems.map((item, index) => (
                  <tr key={index}>
                    <td>
                      <select
                        value={item.item_id}
                        onChange={(e) => {
                          updateItem(index, 'item_id', e.target.value)
                          const selectedItem = items.find(i => i.id === parseInt(e.target.value))
                          if (selectedItem) {
                            updateItem(index, 'description', selectedItem.name)
                          }
                        }}
                      >
                        <option value="">Select Item</option>
                        {items.map((itemOption) => (
                          <option key={itemOption.id} value={itemOption.id}>
                            {itemOption.sku} - {itemOption.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={item.description}
                        onChange={(e) => updateItem(index, 'description', e.target.value)}
                        placeholder="Description"
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.quantity}
                        onChange={(e) => updateItem(index, 'quantity', e.target.value)}
                        placeholder="0.00"
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.unit_price}
                        onChange={(e) => updateItem(index, 'unit_price', e.target.value)}
                        placeholder="0.00"
                      />
                    </td>
                    <td className="line-total">${item.line_total || '0.00'}</td>
                    <td>
                      {invoiceItems.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeItem(index)}
                          className="btn-remove"
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="totals-section">
            <div className="total-row">
              <span>Subtotal:</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            <div className="total-row">
              <label>Tax Amount:</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.tax_amount}
                onChange={(e) => setFormData({ ...formData, tax_amount: e.target.value })}
                className="tax-input"
              />
            </div>
            <div className="total-row">
              <label>Freight:</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.freight}
                onChange={(e) => setFormData({ ...formData, freight: e.target.value })}
                className="tax-input"
              />
            </div>
            <div className="total-row">
              <label>Discount:</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.discount}
                onChange={(e) => setFormData({ ...formData, discount: e.target.value })}
                className="tax-input"
              />
            </div>
            <div className="total-row total-final">
              <span>Total:</span>
              <span>${total.toFixed(2)}</span>
            </div>
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Invoice'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateInvoice






