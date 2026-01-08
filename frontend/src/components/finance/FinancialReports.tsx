import { useState, useEffect } from 'react'
import { getTrialBalance } from '../../api/finance'
import './FinancialReports.css'

function FinancialReports() {
  const [trialBalance, setTrialBalance] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [reportType, setReportType] = useState<'trial-balance' | 'balance-sheet' | 'income-statement'>('trial-balance')

  const loadTrialBalance = async () => {
    try {
      setLoading(true)
      const data = await getTrialBalance()
      setTrialBalance(data)
    } catch (error) {
      console.error('Failed to load trial balance:', error)
      alert('Failed to load trial balance')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (reportType === 'trial-balance') {
      loadTrialBalance()
    }
  }, [reportType])

  const generateBalanceSheet = () => {
    const assets = trialBalance.filter(item => item.account_type === 'asset')
    const liabilities = trialBalance.filter(item => item.account_type === 'liability')
    const equity = trialBalance.filter(item => item.account_type === 'equity')
    
    const totalAssets = assets.reduce((sum, item) => sum + (item.balance > 0 ? item.balance : 0), 0)
    const totalLiabilities = liabilities.reduce((sum, item) => sum + (item.balance > 0 ? item.balance : 0), 0)
    const totalEquity = equity.reduce((sum, item) => sum + (item.balance > 0 ? item.balance : 0), 0)
    
    return { assets, liabilities, equity, totalAssets, totalLiabilities, totalEquity }
  }

  const generateIncomeStatement = () => {
    const revenue = trialBalance.filter(item => item.account_type === 'revenue')
    const expenses = trialBalance.filter(item => item.account_type === 'expense')
    
    const totalRevenue = revenue.reduce((sum, item) => sum + (item.balance > 0 ? item.balance : 0), 0)
    const totalExpenses = expenses.reduce((sum, item) => sum + (item.balance > 0 ? item.balance : 0), 0)
    const netIncome = totalRevenue - totalExpenses
    
    return { revenue, expenses, totalRevenue, totalExpenses, netIncome }
  }

  if (loading) {
    return <div className="loading">Loading report...</div>
  }

  return (
    <div className="financial-reports">
      <div className="reports-header">
        <h2>Financial Reports</h2>
        <div className="report-selector">
          <button
            className={`report-btn ${reportType === 'trial-balance' ? 'active' : ''}`}
            onClick={() => setReportType('trial-balance')}
          >
            Trial Balance
          </button>
          <button
            className={`report-btn ${reportType === 'balance-sheet' ? 'active' : ''}`}
            onClick={() => setReportType('balance-sheet')}
          >
            Balance Sheet
          </button>
          <button
            className={`report-btn ${reportType === 'income-statement' ? 'active' : ''}`}
            onClick={() => setReportType('income-statement')}
          >
            Income Statement
          </button>
        </div>
      </div>

      <div className="report-content">
        {reportType === 'trial-balance' && (
          <div className="trial-balance-report">
            <h3>Trial Balance</h3>
            <table className="report-table">
              <thead>
                <tr>
                  <th>Account Number</th>
                  <th>Account Name</th>
                  <th>Account Type</th>
                  <th className="amount-col">Debits</th>
                  <th className="amount-col">Credits</th>
                  <th className="amount-col">Balance</th>
                </tr>
              </thead>
              <tbody>
                {trialBalance.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="empty-state">
                      No data available. Create journal entries to generate trial balance.
                    </td>
                  </tr>
                ) : (
                  trialBalance.map((item, index) => (
                    <tr key={index}>
                      <td>{item.account_number}</td>
                      <td>{item.account_name}</td>
                      <td>
                        <span className="badge badge-type">{item.account_type}</span>
                      </td>
                      <td className="amount-col">${item.debits.toFixed(2)}</td>
                      <td className="amount-col">${item.credits.toFixed(2)}</td>
                      <td className={`amount-col ${item.balance >= 0 ? 'positive' : 'negative'}`}>
                        ${Math.abs(item.balance).toFixed(2)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              {trialBalance.length > 0 && (
                <tfoot>
                  <tr className="totals-row">
                    <td colSpan={3}>Totals</td>
                    <td className="amount-col">
                      ${trialBalance.reduce((sum, item) => sum + item.debits, 0).toFixed(2)}
                    </td>
                    <td className="amount-col">
                      ${trialBalance.reduce((sum, item) => sum + item.credits, 0).toFixed(2)}
                    </td>
                    <td className="amount-col"></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}

        {reportType === 'balance-sheet' && (
          <div className="balance-sheet-report">
            <h3>Balance Sheet</h3>
            {trialBalance.length === 0 ? (
              <div className="empty-state">No data available</div>
            ) : (
              <>
                {(() => {
                  const { assets, liabilities, equity, totalAssets, totalLiabilities, totalEquity } = generateBalanceSheet()
                  return (
                    <>
                      <div className="balance-sheet-section">
                        <h4>Assets</h4>
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Account</th>
                              <th className="amount-col">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {assets.map((item, index) => (
                              <tr key={index}>
                                <td>{item.account_number} - {item.account_name}</td>
                                <td className="amount-col">${item.balance > 0 ? item.balance.toFixed(2) : '0.00'}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="section-total">
                              <td>Total Assets</td>
                              <td className="amount-col">${totalAssets.toFixed(2)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      <div className="balance-sheet-section">
                        <h4>Liabilities</h4>
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Account</th>
                              <th className="amount-col">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {liabilities.map((item, index) => (
                              <tr key={index}>
                                <td>{item.account_number} - {item.account_name}</td>
                                <td className="amount-col">${item.balance > 0 ? item.balance.toFixed(2) : '0.00'}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="section-total">
                              <td>Total Liabilities</td>
                              <td className="amount-col">${totalLiabilities.toFixed(2)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      <div className="balance-sheet-section">
                        <h4>Equity</h4>
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Account</th>
                              <th className="amount-col">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {equity.map((item, index) => (
                              <tr key={index}>
                                <td>{item.account_number} - {item.account_name}</td>
                                <td className="amount-col">${item.balance > 0 ? item.balance.toFixed(2) : '0.00'}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="section-total">
                              <td>Total Equity</td>
                              <td className="amount-col">${totalEquity.toFixed(2)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      <div className="balance-sheet-total">
                        <div className="total-row">
                          <span>Total Liabilities + Equity</span>
                          <span>${(totalLiabilities + totalEquity).toFixed(2)}</span>
                        </div>
                      </div>
                    </>
                  )
                })()}
              </>
            )}
          </div>
        )}

        {reportType === 'income-statement' && (
          <div className="income-statement-report">
            <h3>Income Statement</h3>
            {trialBalance.length === 0 ? (
              <div className="empty-state">No data available</div>
            ) : (
              <>
                {(() => {
                  const { revenue, expenses, totalRevenue, totalExpenses, netIncome } = generateIncomeStatement()
                  return (
                    <>
                      <div className="income-section">
                        <h4>Revenue</h4>
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Account</th>
                              <th className="amount-col">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {revenue.map((item, index) => (
                              <tr key={index}>
                                <td>{item.account_number} - {item.account_name}</td>
                                <td className="amount-col">${item.balance > 0 ? item.balance.toFixed(2) : '0.00'}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="section-total">
                              <td>Total Revenue</td>
                              <td className="amount-col">${totalRevenue.toFixed(2)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      <div className="income-section">
                        <h4>Expenses</h4>
                        <table className="report-table">
                          <thead>
                            <tr>
                              <th>Account</th>
                              <th className="amount-col">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {expenses.map((item, index) => (
                              <tr key={index}>
                                <td>{item.account_number} - {item.account_name}</td>
                                <td className="amount-col">${item.balance > 0 ? item.balance.toFixed(2) : '0.00'}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="section-total">
                              <td>Total Expenses</td>
                              <td className="amount-col">${totalExpenses.toFixed(2)}</td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      <div className="net-income">
                        <div className="total-row">
                          <span>Net Income</span>
                          <span className={netIncome >= 0 ? 'positive' : 'negative'}>
                            ${Math.abs(netIncome).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </>
                  )
                })()}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default FinancialReports






