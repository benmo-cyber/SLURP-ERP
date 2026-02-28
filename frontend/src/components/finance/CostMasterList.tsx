import { useState, useEffect } from 'react'
import { getCostMasters, deleteCostMaster, updateCostMaster } from '../../api/costMaster'
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
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<CostMaster>>({})

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

  const handleEdit = (cm: CostMaster) => {
    setEditingId(cm.id)
    setEditForm({ ...cm })
  }

  const handleSave = async (id: number) => {
    try {
      await updateCostMaster(id, editForm)
      setEditingId(null)
      setEditForm({})
      loadCostMasters()
    } catch (error: any) {
      console.error('Failed to update cost master:', error)
      alert(error.response?.data?.detail || 'Failed to update cost master')
    }
  }

  const handleCancel = () => {
    setEditingId(null)
    setEditForm({})
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
              <th>Vendor Material</th>
              <th>WWI Product Code</th>
              <th>Vendor</th>
              <th>Price</th>
              <th>Tariff</th>
              <th>Freight</th>
              <th>Cert. Cost</th>
              <th>Landed Cost</th>
              <th>HTS Code</th>
              <th>Origin</th>
              <th>Incoterms</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCostMasters.length === 0 ? (
              <tr>
                <td colSpan={12} className="no-data">No cost master entries found</td>
              </tr>
            ) : (
              filteredCostMasters.map((cm) => {
                const isEditing = editingId === cm.id
                const price = unitToggle === 'lbs' ? cm.price_per_lb : cm.price_per_kg
                const freight = unitToggle === 'lbs' ? (cm.freight_per_kg / 2.20462) : cm.freight_per_kg
                const certCost = unitToggle === 'lbs' ? (cm.cert_cost_per_kg / 2.20462) : cm.cert_cost_per_kg
                const landedCost = unitToggle === 'lbs' ? cm.landed_cost_per_lb : cm.landed_cost_per_kg
                
                return (
                  <tr key={cm.id}>
                    <td>{isEditing ? (
                      <input
                        type="text"
                        value={editForm.vendor_material || ''}
                        onChange={(e) => setEditForm({ ...editForm, vendor_material: e.target.value })}
                        className="edit-input"
                      />
                    ) : cm.vendor_material}</td>
                    <td>{isEditing ? (
                      <input
                        type="text"
                        value={editForm.wwi_product_code || ''}
                        onChange={(e) => setEditForm({ ...editForm, wwi_product_code: e.target.value })}
                        className="edit-input"
                      />
                    ) : (cm.wwi_product_code || '-')}</td>
                    <td>{isEditing ? (
                      <input
                        type="text"
                        value={editForm.vendor || ''}
                        onChange={(e) => setEditForm({ ...editForm, vendor: e.target.value })}
                        className="edit-input"
                      />
                    ) : (cm.vendor || '-')}</td>
                    <td className="read-only">{price ? `$${price.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td>{isEditing ? (
                      <input
                        type="number"
                        step="0.001"
                        value={editForm.tariff ?? cm.tariff}
                        onChange={(e) => setEditForm({ ...editForm, tariff: parseFloat(e.target.value) || 0 })}
                        className="edit-input"
                        title="Tariff rate (e.g., 0.381 for 38.1%)"
                      />
                    ) : (
                      <span title={`${(cm.tariff * 100).toFixed(1)}%`}>
                        {(cm.tariff * 100).toFixed(1)}%
                      </span>
                    )}</td>
                    <td>{isEditing ? (
                      <input
                        type="number"
                        step="0.01"
                        value={unitToggle === 'kg' ? (editForm.freight_per_kg ?? cm.freight_per_kg) : ((editForm.freight_per_kg ?? cm.freight_per_kg) / 2.20462)}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) || 0
                          setEditForm({ 
                            ...editForm, 
                            freight_per_kg: unitToggle === 'kg' ? val : val * 2.20462 
                          })
                        }}
                        className="edit-input"
                      />
                    ) : (freight ? `$${freight.toFixed(2)}/${unitToggle}` : '-')}</td>
                    <td>{certCost ? `$${certCost.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td className="landed-cost">{landedCost ? `$${landedCost.toFixed(2)}/${unitToggle}` : '-'}</td>
                    <td>{isEditing ? (
                      <input
                        type="text"
                        value={editForm.hts_code || ''}
                        onChange={(e) => setEditForm({ ...editForm, hts_code: e.target.value })}
                        className="edit-input"
                      />
                    ) : (cm.hts_code || '-')}</td>
                    <td>{isEditing ? (
                      <input
                        type="text"
                        value={editForm.origin || ''}
                        onChange={(e) => setEditForm({ ...editForm, origin: e.target.value })}
                        className="edit-input"
                      />
                    ) : (cm.origin || '-')}</td>
                    <td>{isEditing ? (
                      <select
                        value={editForm.incoterms || ''}
                        onChange={(e) => setEditForm({ ...editForm, incoterms: e.target.value })}
                        className="edit-input"
                      >
                        <option value="">-</option>
                        <option value="CIF">CIF</option>
                        <option value="FCA">FCA</option>
                        <option value="EXW">EXW</option>
                        <option value="CIP">CIP</option>
                        <option value="FOB">FOB</option>
                        <option value="DDP">DDP</option>
                        <option value="DAP">DAP</option>
                      </select>
                    ) : (cm.incoterms || '-')}</td>
                    <td>
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => handleSave(cm.id)}
                            className="btn btn-success btn-sm"
                            style={{ marginRight: '5px' }}
                          >
                            Save
                          </button>
                          <button
                            onClick={handleCancel}
                            className="btn btn-secondary btn-sm"
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => handleEdit(cm)}
                            className="btn btn-primary btn-sm"
                            style={{ marginRight: '5px' }}
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(cm.id)}
                            className="btn btn-danger btn-sm"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
      
      <div className="cost-master-info">
        <p><strong>Note:</strong> Landed Cost = (Price × (1 + Tariff)) + Freight + Cert. Cost</p>
        <p>Tariff is displayed as a percentage. Edit tariff to update landed cost automatically.</p>
      </div>
    </div>
  )
}

export default CostMasterList
