import { useState, useEffect } from 'react'
import { getAccounts, createJournalEntry } from '../../api/finance'
import { useGodMode } from '../../context/GodModeContext'
import './CreateJournalEntry.css'

interface Account {
  id: number
  account_number: string
  name: string
  account_type: string
}

interface JournalLine {
  account_id: string
  debit_credit: 'debit' | 'credit'
  amount: string
  description: string
}

interface CreateJournalEntryProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateJournalEntry({ onClose, onSuccess }: CreateJournalEntryProps) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [formData, setFormData] = useState({
    entry_date: new Date().toISOString().split('T')[0],
    description: '',
    reference_number: '',
  })
  const [lines, setLines] = useState<JournalLine[]>([
    { account_id: '', debit_credit: 'debit', amount: '', description: '' },
    { account_id: '', debit_credit: 'credit', amount: '', description: '' },
  ])
  const [submitting, setSubmitting] = useState(false)
  const { maxDateForEntry } = useGodMode()

  useEffect(() => {
    loadAccounts()
  }, [])

  const loadAccounts = async () => {
    try {
      const data = await getAccounts()
      setAccounts(data.filter((acc: Account) => acc.is_active))
    } catch (error) {
      console.error('Failed to load accounts:', error)
    }
  }

  const addLine = () => {
    setLines([...lines, { account_id: '', debit_credit: 'debit', amount: '', description: '' }])
  }

  const removeLine = (index: number) => {
    if (lines.length > 2) {
      setLines(lines.filter((_, i) => i !== index))
    }
  }

  const updateLine = (index: number, field: keyof JournalLine, value: any) => {
    const newLines = [...lines]
    newLines[index] = { ...newLines[index], [field]: value }
    setLines(newLines)
  }

  const calculateTotals = () => {
    const totalDebits = lines
      .filter(line => line.debit_credit === 'debit' && line.amount)
      .reduce((sum, line) => sum + parseFloat(line.amount || '0'), 0)
    
    const totalCredits = lines
      .filter(line => line.debit_credit === 'credit' && line.amount)
      .reduce((sum, line) => sum + parseFloat(line.amount || '0'), 0)
    
    return { totalDebits, totalCredits, difference: totalDebits - totalCredits }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validate
    if (!formData.description) {
      alert('Please enter a description')
      return
    }

    const validLines = lines.filter(line => line.account_id && line.amount)
    if (validLines.length < 2) {
      alert('Please add at least 2 lines (one debit and one credit)')
      return
    }

    const { totalDebits, totalCredits, difference } = calculateTotals()
    if (Math.abs(difference) > 0.01) {
      alert(`Debits and credits must be equal. Current difference: $${difference.toFixed(2)}`)
      return
    }

    try {
      setSubmitting(true)
      
      await createJournalEntry({
        entry_date: formData.entry_date,
        description: formData.description,
        reference_number: formData.reference_number || null,
        lines: validLines.map(line => ({
          account_id: parseInt(line.account_id),
          debit_credit: line.debit_credit,
          amount: parseFloat(line.amount),
          description: line.description || '',
        }))
      })
      
      alert('Journal entry created successfully!')
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create journal entry:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to create journal entry')
    } finally {
      setSubmitting(false)
    }
  }

  const { totalDebits, totalCredits, difference } = calculateTotals()

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content journal-entry-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Journal Entry</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="journal-entry-form">
          <div className="form-row">
            <div className="form-group">
              <label>Entry Date *</label>
              <input
                type="date"
                value={formData.entry_date}
                onChange={(e) => setFormData({ ...formData, entry_date: e.target.value })}
                max={maxDateForEntry}
                required
              />
            </div>
            <div className="form-group">
              <label>Reference Number</label>
              <input
                type="text"
                value={formData.reference_number}
                onChange={(e) => setFormData({ ...formData, reference_number: e.target.value })}
                placeholder="Optional"
              />
            </div>
          </div>

          <div className="form-group">
            <label>Description *</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              required
              rows={2}
              placeholder="Enter journal entry description"
            />
          </div>

          <div className="lines-section">
            <div className="lines-header">
              <h3>Journal Entry Lines</h3>
              <button type="button" onClick={addLine} className="btn btn-secondary btn-sm">
                + Add Line
              </button>
            </div>

            <div className="lines-table-wrapper">
              <table className="lines-table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Debit/Credit</th>
                    <th>Amount</th>
                    <th>Description</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <tr key={index}>
                      <td>
                        <select
                          value={line.account_id}
                          onChange={(e) => updateLine(index, 'account_id', e.target.value)}
                          required
                        >
                          <option value="">Select Account</option>
                          {accounts.map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.account_number} - {account.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          value={line.debit_credit}
                          onChange={(e) => updateLine(index, 'debit_credit', e.target.value)}
                          required
                        >
                          <option value="debit">Debit</option>
                          <option value="credit">Credit</option>
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={line.amount}
                          onChange={(e) => updateLine(index, 'amount', e.target.value)}
                          required
                          placeholder="0.00"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={line.description}
                          onChange={(e) => updateLine(index, 'description', e.target.value)}
                          placeholder="Optional"
                        />
                      </td>
                      <td>
                        {lines.length > 2 && (
                          <button
                            type="button"
                            onClick={() => removeLine(index)}
                            className="btn-remove"
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="totals-row">
                    <td colSpan={2} className="totals-label">Totals:</td>
                    <td className="debit-total">${totalDebits.toFixed(2)}</td>
                    <td className="credit-total">${totalCredits.toFixed(2)}</td>
                    <td>
                      <span className={`difference ${Math.abs(difference) < 0.01 ? 'balanced' : 'unbalanced'}`}>
                        {Math.abs(difference) < 0.01 ? '✓ Balanced' : `Difference: $${difference.toFixed(2)}`}
                      </span>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || Math.abs(difference) > 0.01}>
              {submitting ? 'Creating...' : 'Create Journal Entry'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateJournalEntry






