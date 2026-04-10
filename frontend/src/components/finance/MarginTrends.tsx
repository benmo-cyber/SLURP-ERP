import { useState, useEffect, useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { getItems } from '../../api/inventory'
import { getPricingHistory } from '../../api/costMaster'
import { getCustomerPricingHistory } from '../../api/finance'
import './MarginTrends.css'

interface Item {
  id: number
  sku: string
  name: string
  item_type: string
  unit_of_measure: string
}

interface VendorHistoryEntry {
  effective_date: string
  price_per_kg: number | null
  price_per_lb: number | null
  cost_master_detail?: { wwi_product_code: string }
}

interface CustomerHistoryEntry {
  effective_date: string
  sku: string
  unit_price: number
  unit_of_measure: string
}

interface ChartPoint {
  date: string
  [key: string]: string | number
}

const COLORS = {
  cost: '#2563eb',
  price: '#059669',
  margin: '#d97706',
}

function MarginTrends() {
  const [items, setItems] = useState<Item[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [loading, setLoading] = useState(false)
  const [chartData, setChartData] = useState<ChartPoint[]>([])
  const [seriesKeys, setSeriesKeys] = useState<string[]>([])

  const sellableItems = useMemo(
    () => items.filter((i) => i.item_type === 'finished_good' || i.item_type === 'distributed_item'),
    [items]
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await getItems()
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      } catch (e) {
        console.error('Failed to load items', e)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (selectedIds.length === 0) {
      setChartData([])
      setSeriesKeys([])
      return
    }
    const skus = sellableItems.filter((i) => selectedIds.includes(i.id)).map((i) => i.sku)
    if (skus.length === 0) {
      setChartData([])
      setSeriesKeys([])
      return
    }

    let cancelled = false
    setLoading(true)
    Promise.all([getPricingHistory(skus), getCustomerPricingHistory(skus)])
      .then(([vendorHistory, customerHistory]) => {
        if (cancelled) return
        const vh = (Array.isArray(vendorHistory) ? vendorHistory : []) as VendorHistoryEntry[]
        const ch = (Array.isArray(customerHistory) ? customerHistory : []) as CustomerHistoryEntry[]

        const dateMap = new Map<string, Record<string, { cost?: number; priceSum?: number; priceCount?: number }>>()

        vh.forEach((entry) => {
          const sku = entry.cost_master_detail?.wwi_product_code
          if (!sku || !skus.includes(sku)) return
          const date = entry.effective_date?.slice(0, 10)
          if (!date) return
          const costPerLb = entry.price_per_lb ?? (entry.price_per_kg != null ? entry.price_per_kg / 2.20462 : null)
          if (costPerLb == null) return
          if (!dateMap.has(date)) dateMap.set(date, {})
          const row = dateMap.get(date)!
          if (!row[sku]) row[sku] = {}
          row[sku].cost = costPerLb
        })

        ch.forEach((entry) => {
          if (!skus.includes(entry.sku)) return
          const date = entry.effective_date?.slice(0, 10)
          if (!date) return
          let pricePerLb = entry.unit_price
          if (entry.unit_of_measure === 'kg') pricePerLb = entry.unit_price / 2.20462
          if (!dateMap.has(date)) dateMap.set(date, {})
          const row = dateMap.get(date)!
          if (!row[entry.sku]) row[entry.sku] = {}
          const s = row[entry.sku]
          s.priceSum = (s.priceSum ?? 0) + pricePerLb
          s.priceCount = (s.priceCount ?? 0) + 1
        })

        const chart: ChartPoint[] = []
        const keys: string[] = []
        dateMap.forEach((bySku, date) => {
          const point: ChartPoint = { date }
          skus.forEach((sku) => {
            const s = bySku[sku]
            const cost = s?.cost
            const avgPrice = s?.priceCount && s?.priceSum != null ? s.priceSum / s.priceCount : undefined
            const margin = cost != null && avgPrice != null ? avgPrice - cost : undefined
            point[`${sku}_cost`] = cost ?? ''
            point[`${sku}_price`] = avgPrice ?? ''
            point[`${sku}_margin`] = margin ?? ''
            if (cost != null && !keys.includes(`${sku}_cost`)) keys.push(`${sku}_cost`)
            if (avgPrice != null && !keys.includes(`${sku}_price`)) keys.push(`${sku}_price`)
            if (margin != null && !keys.includes(`${sku}_margin`)) keys.push(`${sku}_margin`)
          })
          chart.push(point)
        })
        chart.sort((a, b) => a.date.localeCompare(b.date))
        setChartData(chart)
        setSeriesKeys(keys)
      })
      .catch((e) => {
        if (!cancelled) {
          console.error('Failed to load price history', e)
          setChartData([])
          setSeriesKeys([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [selectedIds, sellableItems])

  const toggleItem = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    )
  }

  const getSeriesColor = (key: string) => {
    if (key.endsWith('_cost')) return COLORS.cost
    if (key.endsWith('_price')) return COLORS.price
    return COLORS.margin
  }

  const getSeriesName = (key: string) => {
    const sku = key.replace(/_cost$|_price$|_margin$/, '')
    const item = sellableItems.find((i) => i.sku === sku)
    const label = key.endsWith('_cost') ? 'Cost' : key.endsWith('_price') ? 'Selling price' : 'Margin'
    return item ? `${item.sku} ${label}` : `${sku} ${label}`
  }

  return (
    <div className="margin-trends">
      <div className="margin-trends-header">
        <h2>Price &amp; margin trends</h2>
        <p className="margin-trends-description">
          Compare vendor cost and customer selling price over time to see how margins change. Select products below.
        </p>
      </div>

      <div className="margin-trends-selection">
        <h3>Select products</h3>
        <div className="margin-trends-items">
          {sellableItems.map((item) => (
            <label key={item.id} className="margin-trends-checkbox">
              <input
                type="checkbox"
                checked={selectedIds.includes(item.id)}
                onChange={() => toggleItem(item.id)}
              />
              <span>{item.sku} – {item.name}</span>
            </label>
          ))}
        </div>
        {sellableItems.length === 0 && (
          <p className="margin-trends-empty">No finished goods or distributed items to show.</p>
        )}
      </div>

      {loading && selectedIds.length > 0 && (
        <div className="margin-trends-loading">Loading history…</div>
      )}

      {!loading && selectedIds.length > 0 && chartData.length > 0 && (
        <div className="margin-trends-chart-card">
          <h3>Cost vs selling price vs margin</h3>
          <p className="margin-trends-legend-hint">Cost = vendor (Cost Master history). Selling price = average customer price. Margin = selling price − cost. All per lb.</p>
          <ResponsiveContainer width="100%" height={420}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" height={72} />
              <YAxis
                tick={{ fontSize: 11 }}
                label={{ value: '$/lb', angle: -90, position: 'insideLeft', style: { fontSize: 12 } }}
              />
              <Tooltip
                formatter={(value: number) => (typeof value === 'number' ? `$${value.toFixed(3)}` : value)}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <Legend />
              {seriesKeys.map((key) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  name={getSeriesName(key)}
                  stroke={getSeriesColor(key)}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && selectedIds.length > 0 && chartData.length === 0 && (
        <div className="margin-trends-empty-state">
          No cost or customer price history for the selected products. Add vendor cost history (via Cost Master / item updates) and customer pricing with effective dates to see trends.
        </div>
      )}

      {selectedIds.length === 0 && (
        <div className="margin-trends-empty-state">Select one or more products above to view cost, selling price, and margin over time.</div>
      )}
    </div>
  )
}

export default MarginTrends
