import { useState, useEffect } from 'react'
import { getIncomeStatement, getFiscalPeriods } from '../../api/finance'
import { formatCurrency } from '../../utils/formatNumber'
import './PLProForma.css'

interface FiscalPeriod {
  id: number
  period_name: string
  start_date: string
  end_date: string
  is_closed: boolean
}

function PLProForma() {
  const [actualData, setActualData] = useState<any>(null)
  const [forecastData, setForecastData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [fiscalPeriods, setFiscalPeriods] = useState<FiscalPeriod[]>([])
  const [selectedFiscalPeriod, setSelectedFiscalPeriod] = useState<number | null>(null)
  const [startDate, setStartDate] = useState<string>(() => {
    const date = new Date()
    date.setMonth(date.getMonth() - 1)
    return date.toISOString().split('T')[0]
  })
  const [endDate, setEndDate] = useState<string>(new Date().toISOString().split('T')[0])
  const [forecastAdjustments, setForecastAdjustments] = useState<{ [key: string]: number }>({})

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

  const loadActualData = async () => {
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
      setActualData(data)
      
      // Initialize forecast data based on actual (can be edited)
      if (data) {
        setForecastData({
          ...data,
          revenues: data.revenues?.map((r: any) => ({
            ...r,
            forecast_amount: r.amount
          })),
          expenses: data.expenses?.map((e: any) => ({
            ...e,
            forecast_amount: e.amount
          }))
        })
      }
    } catch (error) {
      console.error('Failed to load income statement:', error)
      alert('Failed to load income statement')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedFiscalPeriod || (startDate && endDate)) {
      loadActualData()
    }
  }, [selectedFiscalPeriod, startDate, endDate])

  const handleForecastChange = (accountId: number, value: number, type: 'revenue' | 'expense') => {
    setForecastAdjustments({ ...forecastAdjustments, [`${type}_${accountId}`]: value })
    
    if (forecastData) {
      const updated = { ...forecastData }
      if (type === 'revenue') {
        updated.revenues = updated.revenues?.map((r: any) => 
          r.account_id === accountId ? { ...r, forecast_amount: value } : r
        )
      } else {
        updated.expenses = updated.expenses?.map((e: any) => 
          e.account_id === accountId ? { ...e, forecast_amount: value } : e
        )
      }
      
      // Recalculate totals
      updated.total_revenue = updated.revenues?.reduce((sum: number, r: any) => sum + (r.forecast_amount || r.amount || 0), 0) || 0
      updated.total_expenses = updated.expenses?.reduce((sum: number, e: any) => sum + (e.forecast_amount || e.amount || 0), 0) || 0
      updated.net_income = updated.total_revenue - updated.total_expenses
      
      setForecastData(updated)
    }
  }

  return (
    <div className="pl-proforma">
      <div className="pl-header">
        <h2>P&L Pro-Forma</h2>
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
          <button onClick={loadActualData} className="btn btn-primary">Refresh</button>
        </div>
      </div>

      {loading && <div className="loading">Loading P&L...</div>}

      {!loading && forecastData && (
        <div className="pl-content">
          <div className="pl-period">
            <strong>Period:</strong> {forecastData.start_date} to {forecastData.end_date}
            <span style={{ marginLeft: '20px', color: '#666', fontSize: '14px' }}>
              (Edit forecast amounts below)
            </span>
          </div>

          <div className="pl-section">
            <h3>Revenue</h3>
            <table className="pl-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Account Number</th>
                  <th className="amount">Actual</th>
                  <th className="amount">Forecast</th>
                  <th className="amount">Variance</th>
                </tr>
              </thead>
              <tbody>
                {forecastData.revenues?.map((revenue: any) => {
                  const forecast = revenue.forecast_amount || revenue.amount || 0
                  const actual = revenue.amount || 0
                  const variance = forecast - actual
                  return (
                    <tr key={revenue.account_id}>
                      <td>{revenue.account_name}</td>
                      <td>{revenue.account_number}</td>
                      <td className="amount">{formatCurrency(actual)}</td>
                      <td className="amount">
                        <input
                          type="number"
                          step="0.01"
                          value={forecast}
                          onChange={(e) => handleForecastChange(revenue.account_id, parseFloat(e.target.value) || 0, 'revenue')}
                          className="forecast-input"
                        />
                      </td>
                      <td className={`amount ${variance >= 0 ? 'positive' : 'negative'}`}>
                        {formatCurrency(variance)}
                      </td>
                    </tr>
                  )
                })}
                <tr className="total-row">
                  <td colSpan={2}><strong>Total Revenue</strong></td>
                  <td className="amount"><strong>{formatCurrency(actualData?.total_revenue || 0)}</strong></td>
                  <td className="amount"><strong>{formatCurrency(forecastData.total_revenue || 0)}</strong></td>
                  <td className={`amount ${(forecastData.total_revenue - (actualData?.total_revenue || 0)) >= 0 ? 'positive' : 'negative'}`}>
                    <strong>{formatCurrency((forecastData.total_revenue || 0) - (actualData?.total_revenue || 0))}</strong>
                  </td>
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
                  <th className="amount">Actual</th>
                  <th className="amount">Forecast</th>
                  <th className="amount">Variance</th>
                </tr>
              </thead>
              <tbody>
                {forecastData.expenses?.map((expense: any) => {
                  const forecast = expense.forecast_amount || expense.amount || 0
                  const actual = expense.amount || 0
                  const variance = forecast - actual
                  return (
                    <tr key={expense.account_id}>
                      <td>{expense.account_name}</td>
                      <td>{expense.account_number}</td>
                      <td className="amount">{formatCurrency(actual)}</td>
                      <td className="amount">
                        <input
                          type="number"
                          step="0.01"
                          value={forecast}
                          onChange={(e) => handleForecastChange(expense.account_id, parseFloat(e.target.value) || 0, 'expense')}
                          className="forecast-input"
                        />
                      </td>
                      <td className={`amount ${variance >= 0 ? 'positive' : 'negative'}`}>
                        {formatCurrency(variance)}
                      </td>
                    </tr>
                  )
                })}
                <tr className="total-row">
                  <td colSpan={2}><strong>Total Expenses</strong></td>
                  <td className="amount"><strong>{formatCurrency(actualData?.total_expenses || 0)}</strong></td>
                  <td className="amount"><strong>{formatCurrency(forecastData.total_expenses || 0)}</strong></td>
                  <td className={`amount ${(forecastData.total_expenses - (actualData?.total_expenses || 0)) >= 0 ? 'positive' : 'negative'}`}>
                    <strong>{formatCurrency((forecastData.total_expenses || 0) - (actualData?.total_expenses || 0))}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="pl-summary">
            <table className="pl-table">
              <tbody>
                <tr className="summary-row revenue">
                  <td><strong>Total Revenue</strong></td>
                  <td className="amount"><strong>{formatCurrency(forecastData.total_revenue || 0)}</strong></td>
                </tr>
                <tr className="summary-row expense">
                  <td><strong>Total Expenses</strong></td>
                  <td className="amount"><strong>{formatCurrency(forecastData.total_expenses || 0)}</strong></td>
                </tr>
                <tr className="summary-row net-income">
                  <td><strong>Net Income (Forecast)</strong></td>
                  <td className="amount"><strong>{formatCurrency(forecastData.net_income || 0)}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && !forecastData && (
        <div className="no-data">Select a fiscal period or date range to view Pro-Forma P&L</div>
      )}
    </div>
  )
}

export default PLProForma
