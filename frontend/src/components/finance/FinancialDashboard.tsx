import { useState, useEffect } from 'react'
import { 
  LineChart, Line, BarChart, Bar, AreaChart, Area, 
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'
import { getDashboardMetrics, getAccountsReceivableAging, getAccountsPayableAging, getKpis } from '../../api/finance'
import { formatCurrency } from '../../utils/formatNumber'
import './FinancialDashboard.css'

const COLORS = ['#4a90e2', '#50c878', '#f5a623', '#d0021b', '#9013fe', '#bd10e0']

function FinancialDashboard() {
  const [periodType, setPeriodType] = useState<'monthly' | 'quarterly'>('monthly')
  const [monthsBack, setMonthsBack] = useState(12)
  const [metrics, setMetrics] = useState<any>(null)
  const [arAging, setArAging] = useState<any>(null)
  const [apAging, setApAging] = useState<any>(null)
  const [kpis, setKpis] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboardData()
  }, [periodType, monthsBack])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      const [metricsData, arData, apData, kpisData] = await Promise.all([
        getDashboardMetrics({ period_type: periodType, months_back: monthsBack }),
        getAccountsReceivableAging(),
        getAccountsPayableAging(),
        getKpis({ months_back: monthsBack }).catch(() => null)
      ])
      setMetrics(metricsData)
      setArAging(arData)
      setApAging(apData)
      setKpis(kpisData)
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
      alert('Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="dashboard-loading">Loading dashboard...</div>
  }

  if (!metrics) {
    return <div className="dashboard-error">No data available</div>
  }

  const currentMetrics = metrics.current_metrics || {}
  const periods = metrics.periods || []

  // Prepare data for charts
  const revenueExpenseData = periods.map(p => ({
    period: p.period,
    Revenue: p.revenue || 0,
    Expenses: p.expenses || 0,
    Profit: p.profit || 0
  }))

  const profitMarginData = periods.map(p => {
    const margin = p.revenue > 0 ? ((p.profit / p.revenue) * 100) : 0
    return {
      period: p.period,
      'Profit Margin %': margin
    }
  })

  const cashFlowData = periods.map(p => ({
    period: p.period,
    'Cash Flow': p.cash_flow || 0
  }))

  // AR Aging pie chart data
  const arAgingPieData = arAging?.aging_summary ? [
    { name: 'Current', value: arAging.aging_summary.current || 0 },
    { name: '1-30 Days', value: arAging.aging_summary.days_1_30 || 0 },
    { name: '31-60 Days', value: arAging.aging_summary.days_31_60 || 0 },
    { name: '61-90 Days', value: arAging.aging_summary.days_61_90 || 0 },
    { name: 'Over 90 Days', value: arAging.aging_summary.over_90 || 0 }
  ].filter(item => item.value > 0) : []

  // AP Aging pie chart data
  const apAgingPieData = apAging?.aging_summary ? [
    { name: 'Current', value: apAging.aging_summary.current || 0 },
    { name: '1-30 Days', value: apAging.aging_summary.days_1_30 || 0 },
    { name: '31-60 Days', value: apAging.aging_summary.days_31_60 || 0 },
    { name: '61-90 Days', value: apAging.aging_summary.days_61_90 || 0 },
    { name: 'Over 90 Days', value: apAging.aging_summary.over_90 || 0 }
  ].filter(item => item.value > 0) : []

  return (
    <div className="financial-dashboard">
      <div className="dashboard-header">
        <h2>Financial Dashboard</h2>
        <div className="dashboard-controls">
          <select 
            value={periodType} 
            onChange={(e) => setPeriodType(e.target.value as 'monthly' | 'quarterly')}
            className="period-select"
          >
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
          </select>
          <select 
            value={monthsBack} 
            onChange={(e) => setMonthsBack(parseInt(e.target.value))}
            className="period-select"
          >
            <option value="6">Last 6 Months</option>
            <option value="12">Last 12 Months</option>
            <option value="24">Last 24 Months</option>
          </select>
        </div>
      </div>

      {/* Key Metrics Cards */}
      <div className="metrics-cards">
        <div className="metric-card revenue">
          <div className="metric-label">Revenue</div>
          <div className="metric-value">{formatCurrency(currentMetrics.revenue || 0)}</div>
          <div className="metric-period">Current {periodType === 'monthly' ? 'Month' : 'Quarter'}</div>
        </div>
        <div className="metric-card profit">
          <div className="metric-label">Net Profit</div>
          <div className="metric-value">{formatCurrency(currentMetrics.profit || 0)}</div>
          <div className="metric-period">Current {periodType === 'monthly' ? 'Month' : 'Quarter'}</div>
        </div>
        <div className="metric-card cash">
          <div className="metric-label">Cash Balance</div>
          <div className="metric-value">{formatCurrency(metrics.cash_balance || 0)}</div>
          <div className="metric-period">Current</div>
        </div>
        <div className="metric-card ar">
          <div className="metric-label">Accounts Receivable</div>
          <div className="metric-value">{formatCurrency(metrics.ar_total || 0)}</div>
          <div className="metric-period">Outstanding</div>
        </div>
        <div className="metric-card ap">
          <div className="metric-label">Accounts Payable</div>
          <div className="metric-value">{formatCurrency(metrics.ap_total || 0)}</div>
          <div className="metric-period">Outstanding</div>
        </div>
        <div className="metric-card margin">
          <div className="metric-label">Profit Margin</div>
          <div className="metric-value">
            {currentMetrics.revenue > 0 
              ? `${((currentMetrics.profit / currentMetrics.revenue) * 100).toFixed(1)}%`
              : '0%'}
          </div>
          <div className="metric-period">Current {periodType === 'monthly' ? 'Month' : 'Quarter'}</div>
        </div>
      </div>

      {/* Performance KPIs */}
      {kpis?.shipping != null && (
        <div className="dashboard-kpis-section">
          <h3 className="dashboard-kpis-title">Performance</h3>
          <div className="metrics-cards metrics-cards-kpis">
            <div className={`metric-card kpi-on-time ${(kpis.shipping.on_time_shipment_pct ?? 0) >= 95 ? 'kpi-good' : (kpis.shipping.on_time_shipment_pct ?? 0) >= 80 ? 'kpi-medium' : ''}`}>
              <div className="metric-label">On-time shipment</div>
              <div className="metric-value">
                {kpis.shipping.total_shipped > 0 && kpis.shipping.on_time_shipment_pct != null
                  ? `${kpis.shipping.on_time_shipment_pct}%`
                  : '—'}
              </div>
              <div className="metric-period">
                {kpis.shipping.on_time_count} of {kpis.shipping.total_shipped} shipped (last {monthsBack} mo)
              </div>
            </div>
            <div className="metric-card kpi-late">
              <div className="metric-label">Shipped late</div>
              <div className="metric-value">{kpis.shipping.late_count ?? 0}</div>
              <div className="metric-period">
                {kpis.shipping.avg_days_late != null ? `Avg ${kpis.shipping.avg_days_late} days late` : 'Orders past expected date'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Charts Grid */}
      <div className="charts-grid">
        {/* Revenue vs Expenses */}
        <div className="chart-container">
          <h3>Revenue vs Expenses</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={revenueExpenseData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" />
              <YAxis />
              <Tooltip formatter={(value: number) => formatCurrency(value)} />
              <Legend />
              <Area type="monotone" dataKey="Revenue" stackId="1" stroke="#4a90e2" fill="#4a90e2" fillOpacity={0.6} />
              <Area type="monotone" dataKey="Expenses" stackId="2" stroke="#d0021b" fill="#d0021b" fillOpacity={0.6} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Profit Trend */}
        <div className="chart-container">
          <h3>Net Profit Trend</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={revenueExpenseData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" />
              <YAxis />
              <Tooltip formatter={(value: number) => formatCurrency(value)} />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="Profit" 
                stroke="#50c878" 
                strokeWidth={3}
                dot={{ fill: '#50c878', r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Profit Margin */}
        <div className="chart-container">
          <h3>Profit Margin %</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={profitMarginData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" />
              <YAxis />
              <Tooltip formatter={(value: number) => `${value.toFixed(1)}%`} />
              <Legend />
              <Bar dataKey="Profit Margin %" fill="#f5a623" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Cash Flow */}
        <div className="chart-container">
          <h3>Cash Flow</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={cashFlowData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" />
              <YAxis />
              <Tooltip formatter={(value: number) => formatCurrency(value)} />
              <Legend />
              <Area 
                type="monotone" 
                dataKey="Cash Flow" 
                stroke="#9013fe" 
                fill="#9013fe" 
                fillOpacity={0.6} 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* AR Aging */}
        {arAgingPieData.length > 0 && (
          <div className="chart-container">
            <h3>Accounts Receivable Aging</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={arAgingPieData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {arAgingPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* AP Aging */}
        {apAgingPieData.length > 0 && (
          <div className="chart-container">
            <h3>Accounts Payable Aging</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={apAgingPieData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {apAgingPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}

export default FinancialDashboard
