import { useState, useEffect } from 'react'
import { getAccounts } from '../../api/finance'
import CreateAccount from './CreateAccount'
import './GeneralLedger.css'

interface Account {
  id: number
  account_number: string
  name: string
  account_type: string
  parent_account: number | null
  is_active: boolean
  description?: string
}

function GeneralLedger() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateAccount, setShowCreateAccount] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    loadAccounts()
  }, [refreshKey])

  const loadAccounts = async () => {
    try {
      setLoading(true)
      const data = await getAccounts()
      setAccounts(data)
    } catch (error) {
      console.error('Failed to load accounts:', error)
      alert('Failed to load accounts')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSuccess = () => {
    setShowCreateAccount(false)
    setRefreshKey(prev => prev + 1)
  }

  const accountTypes = ['asset', 'liability', 'equity', 'revenue', 'expense']
  const accountTypeLabels: { [key: string]: string } = {
    asset: 'Assets',
    liability: 'Liabilities',
    equity: 'Equity',
    revenue: 'Revenue',
    expense: 'Expenses',
  }

  if (loading) {
    return <div className="loading">Loading chart of accounts...</div>
  }

  return (
    <div className="general-ledger">
      <div className="ledger-header">
        <h2>Chart of Accounts</h2>
        <button onClick={() => setShowCreateAccount(true)} className="btn btn-primary">
          + Create Account
        </button>
      </div>

      <div className="accounts-container">
        {accountTypes.map((type) => {
          const typeAccounts = accounts.filter(acc => acc.account_type === type && acc.is_active)
          if (typeAccounts.length === 0) return null

          return (
            <div key={type} className="account-type-section">
              <h3>{accountTypeLabels[type]}</h3>
              <table className="accounts-table">
                <thead>
                  <tr>
                    <th>Account Number</th>
                    <th>Account Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {typeAccounts.map((account) => (
                    <tr key={account.id}>
                      <td className="account-number">{account.account_number}</td>
                      <td>{account.name}</td>
                      <td>
                        <span className="badge badge-type">{account.account_type}</span>
                      </td>
                      <td>
                        <span className={`status-badge ${account.is_active ? 'active' : 'inactive'}`}>
                          {account.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>{account.description || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}

        {accounts.length === 0 && (
          <div className="empty-state">
            <p>No accounts found. Click "Create Account" to add accounts to your chart of accounts.</p>
          </div>
        )}
      </div>

      {showCreateAccount && (
        <CreateAccount
          onClose={() => setShowCreateAccount(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  )
}

export default GeneralLedger






