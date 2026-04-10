import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { getItems } from '../../api/inventory'
import { getPricingHistory } from '../../api/costMaster'
import { formatAppDate } from '../../utils/appDateFormat'
import './PricingHistory.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
}

interface PricingHistoryEntry {
  id: number
  cost_master: number
  price_per_kg: number | null
  price_per_lb: number | null
  effective_date: string
  changed_by: string | null
  notes: string | null
  cost_master_detail?: {
    wwi_product_code: string
    vendor_material: string
    vendor: string
  }
}

interface ChartDataPoint {
  date: string
  [key: string]: string | number
}

function PricingHistory() {
  const [items, setItems] = useState<Item[]>([])
  const [selectedItems, setSelectedItems] = useState<number[]>([])
  const [history, setHistory] = useState<PricingHistoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [chartData, setChartData] = useState<ChartDataPoint[]>([])

  useEffect(() => {
    loadItems()
  }, [])

  useEffect(() => {
    if (selectedItems.length > 0) {
      loadPricingHistory()
    } else {
      setHistory([])
      setChartData([])
    }
  }, [selectedItems, unitDisplay])

  const loadItems = async () => {
    try {
      const data = await getItems()
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
      alert('Failed to load items')
    }
  }

  const loadPricingHistory = async () => {
    try {
      setLoading(true)
      const selectedItemSkus = items
        .filter(item => selectedItems.includes(item.id))
        .map(item => item.sku)
      
      if (selectedItemSkus.length === 0) {
        setHistory([])
        setChartData([])
        return
      }

      const historyData = await getPricingHistory(selectedItemSkus)
      setHistory(historyData)

      // Transform data for chart
      const transformedData = transformHistoryToChartData(historyData, selectedItemSkus)
      setChartData(transformedData)
    } catch (error) {
      console.error('Failed to load pricing history:', error)
      alert('Failed to load pricing history')
    } finally {
      setLoading(false)
    }
  }

  const transformHistoryToChartData = (historyData: PricingHistoryEntry[], skus: string[]): ChartDataPoint[] => {
    // Group by date and item
    const dateMap = new Map<string, { [sku: string]: number }>()

    historyData.forEach(entry => {
      if (!entry.cost_master_detail) return
      
      const sku = entry.cost_master_detail.wwi_product_code
      if (!skus.includes(sku)) return

      const date = formatAppDate(entry.effective_date)
      const price = unitDisplay === 'kg' 
        ? (entry.price_per_kg || 0)
        : (entry.price_per_lb || 0)

      if (!dateMap.has(date)) {
        dateMap.set(date, {})
      }
      
      const dateData = dateMap.get(date)!
      // Only keep the latest price for each item on each date
      if (!dateData[sku] || price > dateData[sku]) {
        dateData[sku] = price
      }
    })

    // Convert to array and sort by date
    const chartDataArray: ChartDataPoint[] = []
    dateMap.forEach((itemPrices, date) => {
      chartDataArray.push({
        date,
        ...itemPrices
      })
    })

    // Sort by date
    chartDataArray.sort((a, b) => {
      return new Date(a.date).getTime() - new Date(b.date).getTime()
    })

    return chartDataArray
  }

  const handleItemToggle = (itemId: number) => {
    if (selectedItems.includes(itemId)) {
      setSelectedItems(selectedItems.filter(id => id !== itemId))
    } else {
      setSelectedItems([...selectedItems, itemId])
    }
  }

  const getItemName = (sku: string) => {
    const item = items.find(i => i.sku === sku)
    return item ? item.name : sku
  }

  const getItemColor = (index: number) => {
    const colors = [
      '#007bff', '#28a745', '#ffc107', '#dc3545', '#17a2b8',
      '#6f42c1', '#e83e8c', '#fd7e14', '#20c997', '#6c757d'
    ]
    return colors[index % colors.length]
  }

  if (loading && selectedItems.length > 0) {
    return <div className="loading">Loading pricing history...</div>
  }

  return (
    <div className="pricing-history">
      <div className="pricing-history-header">
        <div className="unit-toggle">
          <label>Display Units:</label>
          <button
            className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('lbs')}
          >
            lbs
          </button>
          <button
            className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('kg')}
          >
            kg
          </button>
        </div>
      </div>

      <div className="pricing-history-content">
        <div className="item-selection">
          <h3>Select Items to Compare</h3>
          <div className="items-grid">
            {items.map((item) => (
              <label key={item.id} className="item-checkbox">
                <input
                  type="checkbox"
                  checked={selectedItems.includes(item.id)}
                  onChange={() => handleItemToggle(item.id)}
                />
                <span>{item.name} ({item.sku})</span>
              </label>
            ))}
          </div>
        </div>

        {selectedItems.length > 0 && chartData.length > 0 && (
          <div className="chart-container">
            <h3>Pricing Trends</h3>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="date" 
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis 
                  label={{ value: `Price (${unitDisplay})`, angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value: number) => `$${value.toFixed(2)}`}
                />
                <Legend />
                {items
                  .filter(item => selectedItems.includes(item.id))
                  .map((item, index) => (
                    <Line
                      key={item.id}
                      type="monotone"
                      dataKey={item.sku}
                      name={item.name}
                      stroke={getItemColor(index)}
                      strokeWidth={2}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {selectedItems.length > 0 && chartData.length === 0 && !loading && (
          <div className="empty-state">
            No pricing history found for selected items.
          </div>
        )}

        {selectedItems.length === 0 && (
          <div className="empty-state">
            Select items above to view pricing history comparison.
          </div>
        )}
      </div>
    </div>
  )
}

export default PricingHistory
