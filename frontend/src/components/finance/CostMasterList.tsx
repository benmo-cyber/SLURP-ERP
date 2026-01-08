import { useState, useEffect } from 'react'
import { getCostMasters, deleteCostMaster } from '../../api/costMaster'
import './CostMasterList.css'

interface CostMaster {
  id: number
  vendor_material: string
  wwi_product_code?: string
  price_per_kg?: number
  price_per_lb?: number
  incoterms?: string
  origin?: string
  vendor?: string
  hts_code?: string
  tariff: number
  freight_per_kg: number
  cert_cost_per_kg: number
  landed_cost_per_kg?: number
  landed_cost_per_lb?: number
  margin?: number
  selling_price_per_kg?: number
  selling_price_per_lb?: number
  strength?: string
  minimum?: string
  lead_time?: string
  notes?: string
}

function CostMasterList() {
  const [costMasters, setCostMasters] = useState<CostMaster[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [unitToggle, setUnitToggle] = useState<'lbs' | 'kg'>('lbs')

  useEffect(() => {
    loadCostMasters()
  }, [])

  const loadCostMasters = async () => {
    try {
      setLoading(true)
      const data = await getCostMasters()
      setCostMasters(data)
    } catch (error) {
      console.error('Failed to load cost masters:', error)
      alert('Failed to load cost masters')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this cost master entry?')) {
      return
    }

    try {
      await deleteCostMaster(id)
      loadCostMasters()
    } catch (error: any) {
      console.error('Failed to delete cost master:', error)
      alert(error.response?.data?.detail || 'Failed to delete cost master')
    }
  }

  const filteredCostMasters = costMasters.filter(cm =>
    cm.vendor_material.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (cm.wwi_product_code && cm.wwi_product_code.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (cm.vendor && cm.vendor.toLowerCase().includes(searchTerm.toLowerCase()))
  )

  if (loading) {
    return <div className="loading">Loading cost masters...</div>
  }

  return (
    <div className="cost-master-list">
      <div className="cost-master-header">
        <h2>Cost Master List</h2>
        <div className="cost-master-controls">
          <div className="unit-toggle">
            <button
              className={unitToggle === 'lbs' ? 'active' : ''}
              onClick={() => setUnitToggle('lbs')}
            >
              Price per lb
            </button>
            <button
              className={unitToggle === 'kg' ? 'active' : ''}
              onClick={() => setUnitToggle('kg')}
            >
              Price per kg
            </button>
          </div>
          <input
            type="text"
            placeholder="Search by material, product code, or vendor..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-input"
          />
        </div>
      </div>

      <div className="cost-master-table-container">
        <table className="cost-master-table">
          <thead>
            <tr>
              <th>WWI Product Code</th>
              <th>Vendor</th>
              <th>Price</th>
              <th>Freight Estimate</th>
              <th>Landed Cost</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCostMasters.length === 0 ? (
              <tr>
                <td colSpan={6} className="no-data">No cost master entries found</td>
              </tr>
            ) : (
              filteredCostMasters.map((cm) => {
                const price = unitToggle === 'lbs' ? cm.price_per_lb : cm.price_per_kg
                const freight = unitToggle === 'lbs' ? (cm.freight_per_kg / 2.20462) : cm.freight_per_kg
                const landedCost = unitToggle === 'lbs' ? cm.landed_cost_per_lb : cm.landed_cost_per_kg
                return (
                  <tr key={cm.id}>
                    <td>{cm.wwi_product_code || '-'}</td>
                    <td>{cm.vendor || '-'}</td>
                    <td>{price ? `$${price.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td>{freight ? `$${freight.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td>{landedCost ? `$${landedCost.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td>
                      <button
                        onClick={() => handleDelete(cm.id)}
                        className="btn btn-danger btn-sm"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default CostMasterList

