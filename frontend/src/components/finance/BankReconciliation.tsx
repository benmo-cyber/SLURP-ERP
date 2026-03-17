import React, { useState, useEffect } from 'react'
import { getBankReconciliations, createBankReconciliation, getAccounts } from '../../api/finance'
import { useBackdatedEntry } from '../../context/BackdatedEntryContext'
import './BankReconciliation.css'

interface BankReconRecord {
  id: number
  account: number
  account_number?: string
  account_name?: string
  statement_date: string
  statement_balance: number
  reconciled_at: string | null
  notes: string | null
}

const BankReconciliation: React.FC = () => {
  const [list, setList] = useState<BankReconRecord[]>([])
  const [accounts, setAccounts] = useState<{ id: number; account_number: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ account: 0, statement_date: '', statement_balance: '', notes: '' })

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    try {
      setLoading(true)
      const [reconData, acctData] = await Promise.all([
        getBankReconciliations(),
        getAccounts()
      ])
      setList(Array.isArray(reconData) ? reconData : [])
      const accs = Array.isArray(acctData) ? acctData : (acctData?.results || [])
      const bankAccounts = accs.filter((a: any) => (a.account_number || '').toString().startsWith('10'))
      setAccounts(bankAccounts)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.account || !form.statement_date || form.statement_balance === '') return
    try {
      await createBankReconciliation({
        account: form.account,
        statement_date: form.statement_date,
        statement_balance: parseFloat(form.statement_balance),
        notes: form.notes || undefined
      })
      setForm({ account: 0, statement_date: '', statement_balance: '', notes: '' })
      setShowForm(false)
      load()
    } catch (err) {
      console.error(err)
      alert('Failed to create bank reconciliation')
    }
  }

  const formatCurrency = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
  const formatDate = (d: string) => d ? new Date(d).toLocaleDateString() : ''

  return (
    <div className="bank-reconciliation">
      <div className="bank-recon-header">
        <h2>Bank Reconciliation</h2>
        <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>Add reconciliation</button>
      </div>
      {showForm && (
        <form onSubmit={handleSubmit} className="bank-recon-form">
          <label>Account</label>
          <select value={form.account} onChange={e => setForm(f => ({ ...f, account: parseInt(e.target.value) }))} required>
            <option value={0}>Select account</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.account_number} – {a.name}</option>)}
          </select>
          <label>Statement date</label>
          <input type="date" value={form.statement_date} onChange={e => setForm(f => ({ ...f, statement_date: e.target.value }))} max={maxDateForEntry} required />
          <label>Statement balance</label>
          <input type="number" step="0.01" value={form.statement_balance} onChange={e => setForm(f => ({ ...f, statement_balance: e.target.value }))} required />
          <label>Notes (optional)</label>
          <input type="text" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <div className="form-actions">
            <button type="submit" className="btn btn-primary">Save</button>
            <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}
      {loading ? <p>Loading…</p> : (
        <table className="bank-recon-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Statement date</th>
              <th>Statement balance</th>
              <th>Reconciled</th>
            </tr>
          </thead>
          <tbody>
            {list.map(row => (
              <tr key={row.id}>
                <td>{row.account_number} {row.account_name}</td>
                <td>{formatDate(row.statement_date)}</td>
                <td>{formatCurrency(row.statement_balance)}</td>
                <td>{row.reconciled_at ? formatDate(row.reconciled_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && list.length === 0 && !showForm && <p className="empty-state">No bank reconciliations yet. Add one to compare statement balance to GL.</p>}
    </div>
  )
}

export default BankReconciliation
