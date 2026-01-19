import { useState, useEffect } from 'react'
import { getIncomeStatement, getFiscalPeriods } from '../../api/finance'
import { formatCurrency } from '../../utils/formatNumber'
import './PLActual.css'

interface FiscalPeriod {
  id: number
  period_name: string
  start_date: string
  end_date: string
  is_closed: boolean
}

function PLActual() {
  const [incomeStatement, setIncomeStatement] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [fiscalPeriods, setFiscalPeriods] = useState<FiscalPeriod[]>([])
  const [selectedFiscalPeriod, setSelectedFiscalPeriod] = useState<number | null>(null)
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

  useEffect(() => {
    if (selectedFiscalPeriod || (startDate && endDate)) {
      loadIncomeStatement()
    }
  }, [selectedFiscalPeriod, startDate, endDate])

  return (
    <div className="pl-actual">
      <div className="pl-header">
        <h2>P&L Actual</h2>
        <div className="pl-controls">
          <div className="control-group">
            <label>Fiscal Period:</label>
            <select
              value={selectedFiscalPeriod || ''}
              onChange={(e) => setSelectedFiscalPeriod(e.target.value ? parseInt(e.target.value) : null)}
            >
              <option value="">Select Period</option>
              {fiscalPeriods.map((period) => (
                <option key={period.id} value={period.id}>
                  {period.period_name}
                </option>
              ))}
            </select>
          </div>
          {!selectedFiscalPeriod && (
            <>
              <div className="control-group">
                <label>Start Date:</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div className="control-group">
                <label>End Date:</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </>
          )}
          <button onClick={loadIncomeStatement} className="btn btn-primary">Refresh</button>
        </div>
      </div>

      {loading && <div className="loading">Loading P&L...</div>}

      {!loading && incomeStatement && (
        <div className="pl-content">
          <div className="pl-period">
            <strong>Period:</strong> {incomeStatement.start_date} to {incomeStatement.end_date}
          </div>

          <div className="pl-section">
            <h3>Revenue</h3>
            <table className="pl-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Account Number</th>
                  <th className="amount">Amount</th>
                </tr>
              </thead>
              <tbody>
                {incomeStatement.revenues?.map((revenue: any) => (
                  <tr key={revenue.account_id}>
                    <td>{revenue.account_name}</td>
                    <td>{revenue.account_number}</td>
                    <td className="amount">{formatCurrency(revenue.amount)}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={2}><strong>Total Revenue</strong></td>
                  <td className="amount"><strong>{formatCurrency(incomeStatement.total_revenue || 0)}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="pl-section">
            <h3>Expenses</h3>
            <table className="pl-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Account Number</th>
                  <th className="amount">Amount</th>
                </tr>
              </thead>
              <tbody>
                {incomeStatement.expenses?.map((expense: any) => (
                  <tr key={expense.account_id}>
                    <td>{expense.account_name}</td>
                    <td>{expense.account_number}</td>
                    <td className="amount">{formatCurrency(expense.amount)}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={2}><strong>Total Expenses</strong></td>
                  <td className="amount"><strong>{formatCurrency(incomeStatement.total_expenses || 0)}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="pl-summary">
            <table className="pl-table">
              <tbody>
                <tr className="summary-row revenue">
                  <td><strong>Total Revenue</strong></td>
                  <td className="amount"><strong>{formatCurrency(incomeStatement.total_revenue || 0)}</strong></td>
                </tr>
                <tr className="summary-row expense">
                  <td><strong>Total Expenses</strong></td>
                  <td className="amount"><strong>{formatCurrency(incomeStatement.total_expenses || 0)}</strong></td>
                </tr>
                <tr className="summary-row net-income">
                  <td><strong>Net Income</strong></td>
                  <td className="amount"><strong>{formatCurrency(incomeStatement.net_income || 0)}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !incomeStatement && (
        <div className="no-data">Select a fiscal period or date range to view P&L</div>
      )}
    </div>
  )
}

export default PLActual
