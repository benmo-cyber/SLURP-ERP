import { useState, useEffect } from 'react'
import { getKpis } from '../../api/finance'
import './KPIs.css'

interface KpiShipping {
  on_time_shipment_pct: number | null
  on_time_count: number
  late_count: number
  total_shipped: number
  avg_days_late: number | null
}

interface KpisResponse {
  period: { start_date: string; end_date: string; months_back: number }
  shipping: KpiShipping
}

function KPIs() {
  const [monthsBack, setMonthsBack] = useState(12)
  const [data, setData] = useState<KpisResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadKpis()
  }, [monthsBack])

  const loadKpis = async () => {
    try {
      setLoading(true)
      const res = await getKpis({ months_back: monthsBack })
      setData(res)
    } catch (error) {
      console.error('Failed to load KPIs:', error)
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="kpis-loading">Loading KPIs...</div>
  }

  if (!data) {
    return <div className="kpis-error">Failed to load performance metrics.</div>
  }

  const { period, shipping } = data
  const hasShipping = shipping.total_shipped > 0

  return (
    <div className="kpis-page">
      <div className="kpis-header">
        <h2>Performance KPIs</h2>
        <div className="kpis-controls">
          <label>Period:</label>
          <select
            value={monthsBack}
            onChange={(e) => setMonthsBack(parseInt(e.target.value))}
            className="kpis-period-select"
          >
            <option value={3}>Last 3 months</option>
            <option value={6}>Last 6 months</option>
            <option value={12}>Last 12 months</option>
            <option value={24}>Last 24 months</option>
          </select>
          <span className="kpis-period-dates">
            {period.start_date} – {period.end_date}
          </span>
        </div>
      </div>

      <section className="kpis-section">
        <h3>Shipping performance</h3>
        <div className="kpis-cards">
          <div className={`kpi-card kpi-on-time ${hasShipping && (shipping.on_time_shipment_pct ?? 0) >= 95 ? 'good' : hasShipping ? 'medium' : ''}`}>
            <div className="kpi-label">On-time shipment rate</div>
            <div className="kpi-value">
              {hasShipping && shipping.on_time_shipment_pct != null
                ? `${shipping.on_time_shipment_pct}%`
                : '—'}
            </div>
            <div className="kpi-sublabel">Actual ship date ≤ expected</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Orders shipped on time</div>
            <div className="kpi-value">{shipping.on_time_count}</div>
            <div className="kpi-sublabel">of {shipping.total_shipped} total shipped</div>
          </div>
          <div className="kpi-card kpi-late">
            <div className="kpi-label">Orders shipped late</div>
            <div className="kpi-value">{shipping.late_count}</div>
            {shipping.avg_days_late != null && (
              <div className="kpi-sublabel">Avg {shipping.avg_days_late} days late</div>
            )}
          </div>
        </div>
        {!hasShipping && (
          <p className="kpis-no-data">No shipped orders with expected and actual ship dates in this period.</p>
        )}
      </section>

      <p className="kpis-note">More KPIs (e.g. fulfillment rate, order cycle time) can be added here as needed.</p>
    </div>
  )
}

export default KPIs
