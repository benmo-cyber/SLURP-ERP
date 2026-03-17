import React, { useState, useEffect } from 'react'
import { createPayment, getAccountsPayable, getAccountsReceivable, getAccounts } from '../../api/finance'
import { useBackdatedEntry } from '../../context/BackdatedEntryContext'
import './PaymentEntry.css'

interface PaymentEntryProps {
  onClose: () => void
  onSuccess?: () => void
  paymentType?: 'ap_payment' | 'ar_payment'
  apEntryId?: number
  arEntryId?: number
}

interface APEntry {
  id: number
  vendor_name: string
  invoice_number: string
  balance: number
}

interface AREntry {
  id: number
  customer_name: string
  invoice_number_display: string
  balance: number
}

interface Account {
  id: number
  account_number: string
  name: string
  account_type: string
}

const PaymentEntry: React.FC<PaymentEntryProps> = ({ onClose, onSuccess, paymentType, apEntryId, arEntryId }) => {
  const [formData, setFormData] = useState({
    payment_type: paymentType || 'ap_payment',
    payment_date: new Date().toISOString().split('T')[0],
    payment_method: 'check',
    amount: 0,
    reference_number: '',
    ap_entry: apEntryId || null,
    ar_entry: arEntryId || null,
    account: null as number | null,
    notes: ''
  })
  const [apEntries, setApEntries] = useState<APEntry[]>([])
  const [arEntries, setArEntries] = useState<AREntry[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedEntry, setSelectedEntry] = useState<APEntry | AREntry | null>(null)

  useEffect(() => {
    loadAccounts()
    if (formData.payment_type === 'ap_payment') {
      loadAPEntries()
      if (apEntryId) {
        loadAPEntry(apEntryId)
      }
    } else {
      loadAREntries()
      if (arEntryId) {
        loadAREntry(arEntryId)
      }
    }
  }, [formData.payment_type, apEntryId, arEntryId])

  const loadAccounts = async () => {
    try {
      const data = await getAccounts()
      // Filter for cash/bank accounts (asset accounts)
      const cashAccounts = Array.isArray(data) 
        ? data.filter((acc: Account) => acc.account_type === 'asset' && 
            (acc.name.toLowerCase().includes('cash') || 
             acc.name.toLowerCase().includes('checking') || 
             acc.name.toLowerCase().includes('bank')))
        : []
      setAccounts(cashAccounts)
    } catch (error) {
      console.error('Failed to load accounts:', error)
    }
  }

  const loadAPEntries = async () => {
    try {
      const data = await getAccountsPayable({ status: 'open,partial,overdue' })
      setApEntries(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load AP entries:', error)
    }
  }

  const loadAREntries = async () => {
    try {
      const data = await getAccountsReceivable({ status: 'open,partial,overdue' })
      setArEntries(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load AR entries:', error)
    }
  }

  const loadAPEntry = async (id: number) => {
    try {
      const { getAccountsPayableEntry } = await import('../../api/finance')
      const entry = await getAccountsPayableEntry(id)
      setSelectedEntry(entry)
      setFormData(prev => ({ ...prev, ap_entry: id, amount: entry.balance }))
    } catch (error) {
      console.error('Failed to load AP entry:', error)
    }
  }

  const loadAREntry = async (id: number) => {
    try {
      const { getAccountsReceivableEntry } = await import('../../api/finance')
      const entry = await getAccountsReceivableEntry(id)
      setSelectedEntry(entry)
      setFormData(prev => ({ ...prev, ar_entry: id, amount: entry.balance }))
    } catch (error) {
      console.error('Failed to load AR entry:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.account) {
      alert('Please select a payment account')
      return
    }
    if (formData.amount <= 0) {
      alert('Payment amount must be greater than 0')
      return
    }
    if (formData.payment_type === 'ap_payment' && !formData.ap_entry) {
      alert('Please select an AP entry')
      return
    }
    if (formData.payment_type === 'ar_payment' && !formData.ar_entry) {
      alert('Please select an AR entry')
      return
    }

    try {
      setLoading(true)
      const paymentData = {
        ...formData,
        ap_entry: formData.payment_type === 'ap_payment' ? formData.ap_entry : null,
        ar_entry: formData.payment_type === 'ar_payment' ? formData.ar_entry : null,
      }
      await createPayment(paymentData)
      if (onSuccess) onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to create payment:', error)
      alert(`Failed to create payment: ${error.response?.data?.error || error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleEntrySelect = (entry: APEntry | AREntry) => {
    setSelectedEntry(entry)
    setFormData(prev => ({
      ...prev,
      ap_entry: formData.payment_type === 'ap_payment' ? entry.id : null,
      ar_entry: formData.payment_type === 'ar_payment' ? entry.id : null,
      amount: entry.balance
    }))
  }

  return (
    <div className="payment-entry-modal">
      <div className="payment-entry-content">
        <div className="payment-entry-header">
          <h2>Record Payment</h2>
          <button onClick={onClose} className="btn-close">×</button>
        </div>

        <form onSubmit={handleSubmit} className="payment-entry-form">
          <div className="form-group">
            <label>Payment Type</label>
            <select
              value={formData.payment_type}
              onChange={(e) => {
                setFormData({ ...formData, payment_type: e.target.value as 'ap_payment' | 'ar_payment', ap_entry: null, ar_entry: null })
                setSelectedEntry(null)
              }}
              disabled={!!paymentType}
            >
              <option value="ap_payment">Accounts Payable Payment</option>
              <option value="ar_payment">Accounts Receivable Payment</option>
            </select>
          </div>

          <div className="form-group">
            <label>{formData.payment_type === 'ap_payment' ? 'AP Entry' : 'AR Entry'}</label>
            {formData.payment_type === 'ap_payment' ? (
              <select
                value={formData.ap_entry || ''}
                onChange={(e) => {
                  const entry = apEntries.find(entry => entry.id === parseInt(e.target.value))
                  if (entry) handleEntrySelect(entry)
                }}
                required
              >
                <option value="">Select AP Entry...</option>
                {apEntries.map(entry => (
                  <option key={entry.id} value={entry.id}>
                    {entry.vendor_name} - {entry.invoice_number} (Balance: ${entry.balance.toFixed(2)})
                  </option>
                ))}
              </select>
            ) : (
              <select
                value={formData.ar_entry || ''}
                onChange={(e) => {
                  const entry = arEntries.find(entry => entry.id === parseInt(e.target.value))
                  if (entry) handleEntrySelect(entry)
                }}
                required
              >
                <option value="">Select AR Entry...</option>
                {arEntries.map(entry => (
                  <option key={entry.id} value={entry.id}>
                    {entry.customer_name} - {entry.invoice_number_display || 'N/A'} (Balance: ${entry.balance.toFixed(2)})
                  </option>
                ))}
              </select>
            )}
            {selectedEntry && (
              <div className="selected-entry-info">
                <strong>Selected:</strong> {formData.payment_type === 'ap_payment' 
                  ? (selectedEntry as APEntry).vendor_name 
                  : (selectedEntry as AREntry).customer_name} - 
                Balance: ${selectedEntry.balance.toFixed(2)}
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Payment Date</label>
            <input
              type="date"
              value={formData.payment_date}
              onChange={(e) => setFormData({ ...formData, payment_date: e.target.value })}
              max={maxDateForEntry}
              required
            />
          </div>

          <div className="form-group">
            <label>Payment Method</label>
            <select
              value={formData.payment_method}
              onChange={(e) => setFormData({ ...formData, payment_method: e.target.value })}
              required
            >
              <option value="check">Check</option>
              <option value="wire">Wire Transfer</option>
              <option value="ach">ACH</option>
              <option value="credit_card">Credit Card</option>
              <option value="cash">Cash</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="form-group">
            <label>Amount</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={formData.amount}
              onChange={(e) => setFormData({ ...formData, amount: parseFloat(e.target.value) || 0 })}
              required
            />
            {selectedEntry && formData.amount > selectedEntry.balance && (
              <div className="warning">Amount exceeds balance. This will result in an overpayment.</div>
            )}
          </div>

          <div className="form-group">
            <label>Reference Number</label>
            <input
              type="text"
              placeholder="Check number, wire reference, etc."
              value={formData.reference_number}
              onChange={(e) => setFormData({ ...formData, reference_number: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label>Payment Account</label>
            <select
              value={formData.account || ''}
              onChange={(e) => setFormData({ ...formData, account: parseInt(e.target.value) || null })}
              required
            >
              <option value="">Select Account...</option>
              {accounts.map(account => (
                <option key={account.id} value={account.id}>
                  {account.account_number} - {account.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
            />
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Processing...' : 'Record Payment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default PaymentEntry
