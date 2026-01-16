import { useState, useEffect } from 'react'
import { getTrialBalance, getBalanceSheet, getIncomeStatement, getCashFlowStatement, getFiscalPeriods } from '../../api/finance'
import { formatCurrency } from '../../utils/formatNumber'
import './FinancialReports.css'

interface FiscalPeriod {
  id: number
  period_name: string
  start_date: string
  end_date: string
  is_closed: boolean
}

function FinancialReports() {
  const [trialBalance, setTrialBalance] = useState<any>(null)
  const [balanceSheet, setBalanceSheet] = useState<any>(null)
  const [incomeStatement, setIncomeStatement] = useState<any>(null)
  const [cashFlowStatement, setCashFlowStatement] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [reportType, setReportType] = useState<'trial-balance' | 'balance-sheet' | 'income-statement' | 'cash-flow'>('trial-balance')
  const [fiscalPeriods, setFiscalPeriods] = useState<FiscalPeriod[]>([])
  const [selectedFiscalPeriod, setSelectedFiscalPeriod] = useState<number | null>(null)
  const [asOfDate, setAsOfDate] = useState<string>(new Date().toISOString().split('T')[0])
  const [startDate, setStartDate] = useState<string>(() => {
    const date = new Date()
    date.setMonth(date.getMonth() - 1)
    return date.toISOString().split('T')[0]
  })
  const [endDate, setEndDate] = useState<string>(new Date().toISOString().split('T')[0])

  useEffect(() => {
    loadFiscalPeriods()
  }, [])

  const loadFiscalPeriods = async () => {
    try {
      const data = await getFiscalPeriods()
      setFiscalPeriods(data)
    } catch (error) {
      console.error('Failed to load fiscal periods:', error)
    }
  }

  const loadTrialBalance = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (selectedFiscalPeriod) {
        params.fiscal_period_id = selectedFiscalPeriod
      } else {
        params.as_of_date = asOfDate
      }
      const data = await getTrialBalance(params)
      setTrialBalance(data)
    } catch (error) {
      console.error('Failed to load trial balance:', error)
      alert('Failed to load trial balance')
    } finally {
      setLoading(false)
    }
  }

  const loadBalanceSheet = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (selectedFiscalPeriod) {
        params.fiscal_period_id = selectedFiscalPeriod
      } else {
        params.as_of_date = asOfDate
      }
      const data = await getBalanceSheet(params)
      setBalanceSheet(data)
    } catch (error) {
      console.error('Failed to load balance sheet:', error)
      alert('Failed to load balance sheet')
    } finally {
      setLoading(false)
    }
  }

  const loadIncomeStatement = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (selectedFiscalPeriod) {
        params.fiscal_period_id = selectedFiscalPeriod
      } else {
        params.start_date = startDate
        params.end_date = endDate
      }
      const data = await getIncomeStatement(params)
      setIncomeStatement(data)
    } catch (error) {
      console.error('Failed to load income statement:', error)
      alert('Failed to load income statement')
    } finally {
      setLoading(false)
    }
  }

  const loadCashFlowStatement = async () => {
    try {
      setLoading(true)
      const params: any = {}
      if (selectedFiscalPeriod) {
        params.fiscal_period_id = selectedFiscalPeriod
      } else {
        params.start_date = startDate
        params.end_date = endDate
      }
      const data = await getCashFlowStatement(params)
      setCashFlowStatement(data)
    } catch (error) {
      console.error('Failed to load cash flow statement:', error)
      alert('Failed to load cash flow statement')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (reportType === 'trial-balance') {
      loadTrialBalance()
    } else if (reportType === 'balance-sheet') {
      loadBalanceSheet()
    } else if (reportType === 'income-statement') {
      loadIncomeStatement()
    } else if (reportType === 'cash-flow') {
      loadCashFlowStatement()
    }
  }, [reportType, selectedFiscalPeriod, asOfDate, startDate, endDate])

  const handleRefresh = () => {
    if (reportType === 'trial-balance') {
      loadTrialBalance()
    } else if (reportType === 'balance-sheet') {
      loadBalanceSheet()
    } else if (reportType === 'income-statement') {
      loadIncomeStatement()
    } else if (reportType === 'cash-flow') {
      loadCashFlowStatement()
    }
  }

  return (
    <div className="financial-reports">
      <div className="reports-header">
        <h2>Financial Reports</h2>
        <div className="report-filters">
          <div className="filter-group">
            <label>Report Type:</label>
            <select value={reportType} onChange={(e) => setReportType(e.target.value as any)}>
              <option value="trial-balance">Trial Balance</option>
              <option value="balance-sheet">Balance Sheet</option>
              <option value="income-statement">Income Statement</option>
              <option value="cash-flow">Cash Flow Statement</option>
            </select>
          </div>
          
          <div className="filter-group">
            <label>Fiscal Period:</label>
            <select 
              value={selectedFiscalPeriod || ''} 
              onChange={(e) => setSelectedFiscalPeriod(e.target.value ? parseInt(e.target.value) : null)}
            >
              <option value="">Custom Date Range</option>
              {fiscalPeriods.map(period => (
                <option key={period.id} value={period.id}>
                  {period.period_name} {period.is_closed ? '(Closed)' : '(Open)'}
                </option>
              ))}
            </select>
          </div>

          {!selectedFiscalPeriod && (
            <>
              {(reportType === 'trial-balance' || reportType === 'balance-sheet') && (
                <div className="filter-group">
                  <label>As Of Date:</label>
                  <input 
                    type="date" 
                    value={asOfDate} 
                    onChange={(e) => setAsOfDate(e.target.value)}
                  />
                </div>
              )}
              
              {(reportType === 'income-statement' || reportType === 'cash-flow') && (
                <>
                  <div className="filter-group">
                    <label>Start Date:</label>
                    <input 
                      type="date" 
                      value={startDate} 
                      onChange={(e) => setStartDate(e.target.value)}
                    />
                  </div>
                  <div className="filter-group">
                    <label>End Date:</label>
                    <input 
                      type="date" 
                      value={endDate} 
                      onChange={(e) => setEndDate(e.target.value)}
                    />
                  </div>
                </>
              )}
            </>
          )}

          <button onClick={handleRefresh} className="btn btn-primary">Refresh</button>
        </div>
      </div>

      {loading && <div className="loading">Loading report...</div>}

      {!loading && reportType === 'trial-balance' && trialBalance && (
        <div className="trial-balance-report">
          <h3>Trial Balance {trialBalance.as_of_date && `as of ${trialBalance.as_of_date}`}</h3>
          <table className="financial-table">
            <thead>
              <tr>
                <th>Account Number</th>
                <th>Account Name</th>
                <th>Debit Balance</th>
                <th>Credit Balance</th>
              </tr>
            </thead>
            <tbody>
              {trialBalance.accounts?.map((account: any) => (
                <tr key={account.account_id}>
                  <td>{account.account_number}</td>
                  <td>{account.account_name}</td>
                  <td className="amount">{account.debit_balance > 0 ? formatCurrency(account.debit_balance) : '-'}</td>
                  <td className="amount">{account.credit_balance > 0 ? formatCurrency(account.credit_balance) : '-'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="total-row">
                <td colSpan={2}><strong>Total</strong></td>
                <td className="amount"><strong>{formatCurrency(trialBalance.total_debits || 0)}</strong></td>
                <td className="amount"><strong>{formatCurrency(trialBalance.total_credits || 0)}</strong></td>
              </tr>
            </tfoot>
          </table>
          {trialBalance.is_balanced ? (
            <div className="balance-status balanced">✓ Trial Balance is Balanced</div>
          ) : (
            <div className="balance-status unbalanced">⚠ Trial Balance is NOT Balanced</div>
          )}
        </div>
      )}

      {!loading && reportType === 'balance-sheet' && balanceSheet && (
        <div className="balance-sheet-report">
          <h3>Balance Sheet {balanceSheet.as_of_date && `as of ${balanceSheet.as_of_date}`}</h3>
          <div className="balance-sheet-content">
            <div className="balance-sheet-column">
              <h4>Assets</h4>
              <table className="financial-table">
                <tbody>
                  {balanceSheet.assets?.map((asset: any) => (
                    <tr key={asset.account_id}>
                      <td>{asset.account_name}</td>
                      <td className="amount">{formatCurrency(asset.balance)}</td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td><strong>Total Assets</strong></td>
                    <td className="amount"><strong>{formatCurrency(balanceSheet.total_assets || 0)}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <div className="balance-sheet-column">
              <h4>Liabilities</h4>
              <table className="financial-table">
                <tbody>
                  {balanceSheet.liabilities?.map((liability: any) => (
                    <tr key={liability.account_id}>
                      <td>{liability.account_name}</td>
                      <td className="amount">{formatCurrency(liability.balance)}</td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td><strong>Total Liabilities</strong></td>
                    <td className="amount"><strong>{formatCurrency(balanceSheet.total_liabilities || 0)}</strong></td>
                  </tr>
                </tbody>
              </table>
              
              <h4>Equity</h4>
              <table className="financial-table">
                <tbody>
                  {balanceSheet.equity?.map((equity: any) => (
                    <tr key={equity.account_id}>
                      <td>{equity.account_name}</td>
                      <td className="amount">{formatCurrency(equity.balance)}</td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td><strong>Total Equity</strong></td>
                    <td className="amount"><strong>{formatCurrency(balanceSheet.total_equity || 0)}</strong></td>
                  </tr>
                </tbody>
              </table>
              
              <table className="financial-table">
                <tbody>
                  <tr className="total-row">
                    <td><strong>Total Liabilities & Equity</strong></td>
                    <td className="amount"><strong>{formatCurrency(balanceSheet.total_liabilities_and_equity || 0)}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          {balanceSheet.is_balanced ? (
            <div className="balance-status balanced">✓ Balance Sheet is Balanced</div>
          ) : (
            <div className="balance-status unbalanced">⚠ Balance Sheet is NOT Balanced</div>
          )}
        </div>
      )}

      {!loading && reportType === 'income-statement' && incomeStatement && (
        <div className="income-statement-report">
          <h3>Income Statement</h3>
          {incomeStatement.start_date && incomeStatement.end_date && (
            <p className="report-period">
              Period: {incomeStatement.start_date} to {incomeStatement.end_date}
            </p>
          )}
          <table className="financial-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr className="section-header">
                <td colSpan={2}><strong>Revenue</strong></td>
              </tr>
              {incomeStatement.revenues?.map((revenue: any) => (
                <tr key={revenue.account_id}>
                  <td>{revenue.account_name}</td>
                  <td className="amount">{formatCurrency(revenue.amount)}</td>
                </tr>
              ))}
              <tr className="total-row">
                <td><strong>Total Revenue</strong></td>
                <td className="amount"><strong>{formatCurrency(incomeStatement.total_revenue || 0)}</strong></td>
              </tr>
              
              <tr className="section-header">
                <td colSpan={2}><strong>Expenses</strong></td>
              </tr>
              {incomeStatement.expenses?.map((expense: any) => (
                <tr key={expense.account_id}>
                  <td>{expense.account_name}</td>
                  <td className="amount">{formatCurrency(expense.amount)}</td>
                </tr>
              ))}
              <tr className="total-row">
                <td><strong>Total Expenses</strong></td>
                <td className="amount"><strong>{formatCurrency(incomeStatement.total_expenses || 0)}</strong></td>
              </tr>
            </tbody>
            <tfoot>
              <tr className="net-income-row">
                <td><strong>Net Income</strong></td>
                <td className="amount">
                  <strong className={incomeStatement.net_income >= 0 ? 'positive' : 'negative'}>
                    {formatCurrency(incomeStatement.net_income || 0)}
                  </strong>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {!loading && reportType === 'cash-flow' && cashFlowStatement && (
        <div className="cash-flow-report">
          <h3>Cash Flow Statement</h3>
          {cashFlowStatement.start_date && cashFlowStatement.end_date && (
            <p className="report-period">
              Period: {cashFlowStatement.start_date} to {cashFlowStatement.end_date}
            </p>
          )}
          <table className="financial-table">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr className="section-header">
                <td colSpan={2}><strong>Operating Activities</strong></td>
              </tr>
              {cashFlowStatement.operating_activities?.map((activity: any, index: number) => (
                <tr key={index}>
                  <td>{activity.description}</td>
                  <td className="amount">{formatCurrency(activity.amount)}</td>
                </tr>
              ))}
              <tr className="total-row">
                <td><strong>Net Cash from Operations</strong></td>
                <td className="amount"><strong>{formatCurrency(cashFlowStatement.cash_flow_operations || 0)}</strong></td>
              </tr>
              
              <tr className="section-header">
                <td colSpan={2}><strong>Investing Activities</strong></td>
              </tr>
              {cashFlowStatement.investing_activities?.map((activity: any, index: number) => (
                <tr key={index}>
                  <td>{activity.description}</td>
                  <td className="amount">{formatCurrency(activity.amount)}</td>
                </tr>
              ))}
              {(!cashFlowStatement.investing_activities || cashFlowStatement.investing_activities.length === 0) && (
                <tr>
                  <td>No investing activities</td>
                  <td className="amount">-</td>
                </tr>
              )}
              <tr className="total-row">
                <td><strong>Net Cash from Investing</strong></td>
                <td className="amount"><strong>{formatCurrency(cashFlowStatement.cash_flow_investing || 0)}</strong></td>
              </tr>
              
              <tr className="section-header">
                <td colSpan={2}><strong>Financing Activities</strong></td>
              </tr>
              {cashFlowStatement.financing_activities?.map((activity: any, index: number) => (
                <tr key={index}>
                  <td>{activity.description}</td>
                  <td className="amount">{formatCurrency(activity.amount)}</td>
                </tr>
              ))}
              {(!cashFlowStatement.financing_activities || cashFlowStatement.financing_activities.length === 0) && (
                <tr>
                  <td>No financing activities</td>
                  <td className="amount">-</td>
                </tr>
              )}
              <tr className="total-row">
                <td><strong>Net Cash from Financing</strong></td>
                <td className="amount"><strong>{formatCurrency(cashFlowStatement.cash_flow_financing || 0)}</strong></td>
              </tr>
            </tbody>
            <tfoot>
              <tr className="net-income-row">
                <td><strong>Net Change in Cash</strong></td>
                <td className="amount">
                  <strong className={cashFlowStatement.net_cash_flow >= 0 ? 'positive' : 'negative'}>
                    {formatCurrency(cashFlowStatement.net_cash_flow || 0)}
                  </strong>
                </td>
              </tr>
              <tr>
                <td>Beginning Cash</td>
                <td className="amount">{formatCurrency(cashFlowStatement.beginning_cash || 0)}</td>
              </tr>
              <tr className="total-row">
                <td><strong>Ending Cash</strong></td>
                <td className="amount"><strong>{formatCurrency(cashFlowStatement.ending_cash || 0)}</strong></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default FinancialReports
