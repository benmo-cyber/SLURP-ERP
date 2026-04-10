import React, { useState, useEffect } from 'react'
import { getCostMasters, deleteCostMaster, updateCostMaster, getCostMasterActuals } from '../../api/costMaster'
import './CostMasterList.css'

const LBS_PER_KG = 2.20462

type ActualsMap = Record<number, {
  avg_tariff_pct?: number
  avg_freight_per_kg?: number
  actual_landed_per_kg?: number
  estimated_landed_per_kg?: number | null
  comparison: 'over' | 'under' | 'ok'
  shipments_count: number
}>

interface CostMaster {
  id: number
  vendor_material: string
  wwi_product_code?: string
  price_per_kg?: number
  price_per_lb?: number
  unit_of_measure?: string | null
  incoterms?: string
  incoterms_place?: string | null
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
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null)
  const [actuals, setActuals] = useState<ActualsMap>({})
  type CostMasterSortKey = 'vendor' | 'origin' | 'vendor_material' | 'wwi_product_code' | null
  const [sort, setSort] = useState<{ key: CostMasterSortKey; dir: 'asc' | 'desc' }>({ key: 'vendor_material', dir: 'asc' })

  useEffect(() => {
    loadCostMasters()
  }, [])

  const loadCostMasters = async () => {
    try {
      setLoading(true)
      const data = await getCostMasters()
      setCostMasters(data)
      try {
        const ids = (Array.isArray(data) ? data : []).map((c: CostMaster) => c.id)
        const actualsData = await getCostMasterActuals(ids.length ? ids : undefined)
        setActuals(actualsData || {})
      } catch {
        setActuals({})
      }
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

  const sortCostMasters = (list: CostMaster[]) => {
    if (!sort.key) return list
    return [...list].sort((a, b) => {
      const aVal = (a[sort.key!] ?? '') as string
      const bVal = (b[sort.key!] ?? '') as string
      const cmp = String(aVal).localeCompare(String(bVal), undefined, { sensitivity: 'base' })
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }

  const handleSort = (key: NonNullable<CostMasterSortKey>) => {
    setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  const sortedCostMasters = sortCostMasters(filteredCostMasters)

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
              <th className="sortable" onClick={() => handleSort('vendor_material')} title="Sort by Vendor Material">
                Vendor Material {sort.key === 'vendor_material' && (sort.dir === 'asc' ? '↑' : '↓')}
              </th>
              <th className="sortable" onClick={() => handleSort('wwi_product_code')} title="Sort by WWI Product Code">
                WWI Product Code {sort.key === 'wwi_product_code' && (sort.dir === 'asc' ? '↑' : '↓')}
              </th>
              <th className="sortable" onClick={() => handleSort('vendor')} title="Sort by Vendor">
                Vendor {sort.key === 'vendor' && (sort.dir === 'asc' ? '↑' : '↓')}
              </th>
              <th>Price</th>
              <th>Tariff</th>
              <th>Freight</th>
              <th>Landed Cost</th>
              <th>HTS Code</th>
              <th className="sortable" onClick={() => handleSort('origin')} title="Sort by Origin">
                Origin {sort.key === 'origin' && (sort.dir === 'asc' ? '↑' : '↓')}
              </th>
              <th>Incoterms</th>
              <th>Incoterms place</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCostMasters.length === 0 ? (
              <tr>
                <td colSpan={12} className="no-data">No cost master entries found</td>
              </tr>
            ) : (
              sortedCostMasters.map((cm) => {
                const isEditing = editingId === cm.id
                const isEa = (cm.unit_of_measure || '').toLowerCase() === 'ea'
                const priceUnit = isEa ? 'EA' : unitToggle
                const price = isEa ? (cm.price_per_lb ?? cm.price_per_kg) : (unitToggle === 'lbs' ? cm.price_per_lb : cm.price_per_kg)
                const freight = isEa ? cm.freight_per_kg : (unitToggle === 'lbs' ? (cm.freight_per_kg / 2.20462) : cm.freight_per_kg)
                const landedCost = isEa ? (cm.landed_cost_per_kg ?? cm.landed_cost_per_lb) : (unitToggle === 'lbs' ? cm.landed_cost_per_lb : cm.landed_cost_per_kg)
                const act = actuals[cm.id]
                const hasActuals = act && act.shipments_count > 0
                const isExpanded = expandedRowId === cm.id
                const landedCostClass = act?.comparison === 'over' ? 'landed-cost landed-cost-over' : act?.comparison === 'under' ? 'landed-cost landed-cost-under' : 'landed-cost'

                return (
                  <React.Fragment key={cm.id}>
                  <tr>
                    <td>
                      {hasActuals && !isEditing && (
                        <button
                          type="button"
                          className="cost-master-expand-btn"
                          onClick={() => setExpandedRowId(isExpanded ? null : cm.id)}
                          title={isExpanded ? 'Collapse actuals' : 'Show cost actuals'}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded ? '▼' : '▶'}
                        </button>
                      )}
                      {isEditing ? (
                        <input
                          type="text"
                          value={editForm.vendor_material || ''}
                          onChange={(e) => setEditForm({ ...editForm, vendor_material: e.target.value })}
                          className="edit-input"
                        />
                      ) : cm.vendor_material}
                    </td>
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
                    <td className="read-only">{price != null ? `$${price.toFixed(2)}/${priceUnit}` : '-'}</td>
                    <td>{isEditing ? (
                      <span className="edit-tariff-wrap">
                        <input
                          type="number"
                          step="0.1"
                          min={0}
                          value={((editForm.tariff ?? cm.tariff) * 100)}
                          onChange={(e) => setEditForm({ ...editForm, tariff: (parseFloat(e.target.value) || 0) / 100 })}
                          className="edit-input"
                          title="Tariff % (e.g. 38.1 for 38.1%)"
                          style={{ width: '4rem' }}
                        />
                        <span className="edit-tariff-suffix">%</span>
                      </span>
                    ) : (
                      <span title={`${(cm.tariff * 100).toFixed(1)}%`}>
                        {(cm.tariff * 100).toFixed(1)}%
                      </span>
                    )}</td>
                    <td>{isEditing ? (
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        value={isEa ? (editForm.freight_per_kg ?? cm.freight_per_kg) : (unitToggle === 'kg' ? (editForm.freight_per_kg ?? cm.freight_per_kg) : ((editForm.freight_per_kg ?? cm.freight_per_kg) / 2.20462))}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) || 0
                          setEditForm({
                            ...editForm,
                            freight_per_kg: isEa ? val : (unitToggle === 'kg' ? val : val * 2.20462)
                          })
                        }}
                        className="edit-input"
                        title={isEa ? 'Freight per EA' : `Freight per ${unitToggle}`}
                        style={{ width: '5rem' }}
                      />
                    ) : (freight ? `$${freight.toFixed(2)}/${priceUnit}` : '-')}</td>
                    <td className={landedCostClass}>{landedCost != null ? `$${landedCost.toFixed(2)}/${priceUnit}` : '-'}</td>
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
                        title="Incoterm (e.g. FCA, CIF)"
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
                    <td>{isEditing ? (
                      <input
                        type="text"
                        placeholder="e.g. Long Beach, CA"
                        value={editForm.incoterms_place ?? cm.incoterms_place ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, incoterms_place: e.target.value || undefined })}
                        className="edit-input"
                        title="Incoterms point / named place (pricing from vendor)"
                      />
                    ) : (cm.incoterms_place || '-')}</td>
                    <td>
                      <div className="cost-master-actions">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleSave(cm.id)}
                              className="cost-master-btn cost-master-btn-save"
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              onClick={handleCancel}
                              className="cost-master-btn cost-master-btn-cancel"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => handleEdit(cm)}
                              className="cost-master-btn cost-master-btn-edit"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDelete(cm.id)}
                              className="cost-master-btn cost-master-btn-delete"
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isExpanded && hasActuals && act && (
                    <tr key={`${cm.id}-actuals`} className="cost-master-actuals-row">
                      <td colSpan={12} className="cost-master-actuals-cell">
                        <div className="cost-master-actuals-inner">
                          <strong>Cost actuals</strong> (from {act.shipments_count} shipment{act.shipments_count !== 1 ? 's' : ''} in A/P):
                          <span className="cost-master-actuals-stats">
                            Avg tariff {act.avg_tariff_pct != null ? `${act.avg_tariff_pct.toFixed(1)}%` : '—'}
                            {' · '}
                            Avg freight {act.avg_freight_per_kg != null
                              ? `$${isEa ? act.avg_freight_per_kg.toFixed(2) : (unitToggle === 'lbs' ? (act.avg_freight_per_kg / LBS_PER_KG).toFixed(2) : act.avg_freight_per_kg.toFixed(2))}/${priceUnit}`
                              : '—'}
                            {' · '}
                            Actual landed {act.actual_landed_per_kg != null
                              ? `$${isEa ? act.actual_landed_per_kg.toFixed(2) : (unitToggle === 'lbs' ? (act.actual_landed_per_kg / LBS_PER_KG).toFixed(2) : act.actual_landed_per_kg.toFixed(2))}/${priceUnit}`
                              : '—'}
                            {' · '}
                            Estimate {act.estimated_landed_per_kg != null
                              ? `$${isEa ? act.estimated_landed_per_kg.toFixed(2) : (unitToggle === 'lbs' ? (act.estimated_landed_per_kg / LBS_PER_KG).toFixed(2) : act.estimated_landed_per_kg.toFixed(2))}/${priceUnit}`
                              : '—'}
                          </span>
                          <span className={`cost-master-actuals-badge cost-master-actuals-${act.comparison}`}>
                            {act.comparison === 'over' ? 'Actual above estimate — review' : act.comparison === 'under' ? 'Actual below estimate' : 'Within tolerance'}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
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
