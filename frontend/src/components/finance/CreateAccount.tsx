import { useState, useEffect } from 'react'
import { getAccounts, createAccount } from '../../api/finance'
import './CreateAccount.css'

interface CreateAccountProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateAccount({ onClose, onSuccess }: CreateAccountProps) {
  const [parentAccounts, setParentAccounts] = useState<any[]>([])
  const [formData, setFormData] = useState({
    account_number: '',
    name: '',
    account_type: 'asset',
    parent_account: '',
    description: '',
  })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    loadParentAccounts()
  }, [])

  const loadParentAccounts = async () => {
    try {
      const data = await getAccounts()
      setParentAccounts(data.filter((acc: any) => acc.is_active))
    } catch (error) {
      console.error('Failed to load accounts:', error)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.account_number || !formData.name) {
      alert('Please fill in all required fields')
      return
    }

    try {
      setSubmitting(true)
      
      await createAccount({
        account_number: formData.account_number,
        name: formData.name,
        account_type: formData.account_type,
        parent_account: formData.parent_account || null,
        description: formData.description || null,
        is_active: true,
      })
      
      alert('Account created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create account:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create account')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-account-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Account</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="account-form">
          <div className="form-group">
            <label>Account Number *</label>
            <input
              type="text"
              value={formData.account_number}
              onChange={(e) => setFormData({ ...formData, account_number: e.target.value })}
              required
              placeholder="e.g., 1000, 2000, 4000"
            />
          </div>

          <div className="form-group">
            <label>Account Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
              placeholder="e.g., Cash, Accounts Receivable"
            />
          </div>

          <div className="form-group">
            <label>Account Type *</label>
            <select
              value={formData.account_type}
              onChange={(e) => setFormData({ ...formData, account_type: e.target.value })}
              required
            >
              <option value="asset">Asset</option>
              <option value="liability">Liability</option>
              <option value="equity">Equity</option>
              <option value="revenue">Revenue</option>
              <option value="expense">Expense</option>
            </select>
          </div>

          <div className="form-group">
            <label>Parent Account (Optional)</label>
            <select
              value={formData.parent_account}
              onChange={(e) => setFormData({ ...formData, parent_account: e.target.value })}
            >
              <option value="">None</option>
              {parentAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_number} - {account.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              placeholder="Optional description"
            />
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateAccount






