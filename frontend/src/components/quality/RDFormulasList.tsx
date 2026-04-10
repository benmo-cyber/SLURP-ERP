import { useState, useEffect } from 'react'
import { getRDFormulas, getRDFormula, createRDFormula, updateRDFormula, deleteRDFormula } from '../../api/rdFormulas'
import { getItems } from '../../api/inventory'
import { getCostMasterByProductCode } from '../../api/costMaster'
import { formatAppDate } from '../../utils/appDateFormat'
import './RDFormulasList.css'

const LB_PER_KG = 2.20462

function roundMoney2(n: number): number {
  return Math.round(n * 100) / 100
}

/** Catalog item price → $/lb for R&D line (aligned with PO pricing: lbs as-is, kg → ÷ LB_PER_KG). */
function pricePerLbFromCatalogItem(item: {
  price?: number | null
  unit_of_measure?: string | null
}): number | null {
  const p = item.price
  if (p == null || p <= 0 || !Number.isFinite(p)) return null
  const u = (item.unit_of_measure || 'lbs').toLowerCase()
  if (u === 'lbs' || u === 'lb') return roundMoney2(p)
  if (u === 'kg') return roundMoney2(p / LB_PER_KG)
  if (u === 'ea') return roundMoney2(p)
  return roundMoney2(p)
}

async function pricePerLbFromCostMasterFallback(item: { sku: string; vendor?: string | null }): Promise<number | null> {
  try {
    let cm = await getCostMasterByProductCode(item.sku, item.vendor || undefined)
    if (!cm) cm = await getCostMasterByProductCode(item.sku)
    if (!cm) return null
    if (cm.price_per_lb != null && cm.price_per_lb > 0) return roundMoney2(cm.price_per_lb)
    if (cm.price_per_kg != null && cm.price_per_kg > 0) return roundMoney2(cm.price_per_kg / LB_PER_KG)
    return null
  } catch {
    return null
  }
}

const LINE_TYPE_ORDER: { line_type: 'ingredient' | 'packaging' | 'labor'; sequence: number; rowId: string }[] = [
  { line_type: 'ingredient', sequence: 1, rowId: 'R1' },
  { line_type: 'ingredient', sequence: 2, rowId: 'R2' },
  { line_type: 'ingredient', sequence: 3, rowId: 'R3' },
  { line_type: 'ingredient', sequence: 4, rowId: 'R4' },
  { line_type: 'ingredient', sequence: 5, rowId: 'R5' },
  { line_type: 'packaging', sequence: 1, rowId: 'P1' },
  { line_type: 'packaging', sequence: 2, rowId: 'P2' },
  { line_type: 'packaging', sequence: 3, rowId: 'P3' },
  { line_type: 'labor', sequence: 1, rowId: 'Labor' },
]

interface RDFormulaLine {
  id?: number
  line_type: string
  sequence: number
  item?: { id: number; sku: string; name: string } | null
  item_id?: number | null
  description: string
  composition_pct: number | null
  price_per_lb: number | null
  labor_flat_amount: number | null
  formula_cost?: number | null
}

interface RDFormula {
  id: number
  name: string
  status: string
  notes: string | null
  total_cost_per_lb?: number
  lines: RDFormulaLine[]
  updated_at: string
}

function emptyLine(lineType: string, seq: number): RDFormulaLine {
  return {
    line_type: lineType,
    sequence: seq,
    description: '',
    composition_pct: null,
    price_per_lb: null,
    labor_flat_amount: lineType === 'labor' ? 0 : null,
  }
}

interface CatalogItemOption {
  id: number
  sku: string
  name: string
  price?: number | null
  unit_of_measure?: string | null
  vendor?: string | null
}

function RDFormulasList() {
  const [list, setList] = useState<RDFormula[]>([])
  const [items, setItems] = useState<CatalogItemOption[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState({ name: '', status: 'draft', notes: '' })
  const [lines, setLines] = useState<RDFormulaLine[]>(() =>
    LINE_TYPE_ORDER.map(({ line_type, sequence }) => emptyLine(line_type, sequence))
  )

  useEffect(() => {
    loadList()
    loadItems()
  }, [])

  const loadList = async () => {
    try {
      setLoading(true)
      const data = await getRDFormulas()
      setList(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error(e)
      alert('Failed to load R&D formulas')
    } finally {
      setLoading(false)
    }
  }

  const loadItems = async () => {
    try {
      const data = await getItems()
      const raw = (data?.results ?? data) || []
      setItems(
        raw
          .filter((i: any) => i.item_type === 'raw_material' || i.item_type === 'distributed_item')
          .map((i: any) => ({
            id: i.id,
            sku: i.sku,
            name: i.name,
            price: i.price ?? null,
            unit_of_measure: i.unit_of_measure ?? null,
            vendor: i.vendor ?? null,
          }))
      )
    } catch (e) {
      console.error(e)
    }
  }

  const openCreate = () => {
    setEditingId(null)
    setForm({ name: '', status: 'draft', notes: '' })
    setLines(LINE_TYPE_ORDER.map(({ line_type, sequence }) => emptyLine(line_type, sequence)))
    setShowForm(true)
  }

  const openEdit = async (id: number) => {
    try {
      const rd = await getRDFormula(id) as RDFormula
      setForm({ name: rd.name, status: rd.status, notes: rd.notes || '' })
      const byKey = (rd.lines || []).reduce((acc: Record<string, RDFormulaLine>, l) => {
        acc[`${l.line_type}-${l.sequence}`] = l
        return acc
      }, {})
      setLines(
        LINE_TYPE_ORDER.map(({ line_type, sequence }) => {
          const key = `${line_type}-${sequence}`
          return byKey[key] ? { ...byKey[key], item_id: byKey[key].item?.id ?? byKey[key].item_id } : emptyLine(line_type, sequence)
        })
      )
      setEditingId(id)
      setShowForm(true)
    } catch (e) {
      console.error(e)
      alert('Failed to load R&D formula')
    }
  }

  const closeForm = () => {
    setShowForm(false)
    setEditingId(null)
  }

  const updateLine = (idx: number, updates: Partial<RDFormulaLine>) => {
    const next = [...lines]
    next[idx] = { ...next[idx], ...updates }
    setLines(next)
  }

  const getFormulaCost = (line: RDFormulaLine): number | null => {
    if (line.line_type === 'labor') return line.labor_flat_amount ?? null
    if (line.composition_pct != null && line.price_per_lb != null) return Math.round((line.composition_pct / 100) * line.price_per_lb * 100) / 100
    return null
  }

  const totalCost = lines.reduce((sum, l) => sum + (getFormulaCost(l) ?? 0), 0)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      alert('Enter a product name')
      return
    }
    const payload = {
      name: form.name.trim(),
      status: form.status,
      notes: form.notes.trim() || undefined,
      lines: lines.map((l, i) => {
        const { line_type, sequence } = LINE_TYPE_ORDER[i]
        return {
          line_type,
          sequence,
          item_id: l.item_id || l.item?.id || null,
          description: l.description || '',
          composition_pct: l.line_type === 'labor' ? null : l.composition_pct,
          price_per_lb: l.line_type === 'labor' ? null : l.price_per_lb,
          labor_flat_amount: l.line_type === 'labor' ? (l.labor_flat_amount ?? 0) : null,
          notes: l.notes || null,
        }
      }),
    }
    try {
      if (editingId) {
        await updateRDFormula(editingId, payload)
        alert('R&D formula updated')
      } else {
        await createRDFormula(payload)
        alert('R&D formula created')
      }
      closeForm()
      loadList()
    } catch (err: any) {
      console.error(err)
      alert(err.response?.data?.detail || err.message || 'Save failed')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this R&D formula?')) return
    try {
      await deleteRDFormula(id)
      loadList()
    } catch (e) {
      console.error(e)
      alert('Delete failed')
    }
  }

  if (loading) return <div className="rd-formulas-loading">Loading R&D formulas...</div>

  return (
    <div className="rd-formulas-list">
      <div className="rd-formulas-header">
        <h2>R&D Formulas</h2>
        <p className="rd-formulas-subtitle">Pre-commercialization formulas for cost estimation. When approved, use Create Finished Good and select this formula to pre-fill.</p>
        <div className="rd-formulas-actions">
          <button type="button" onClick={openCreate} className="btn btn-primary">Add R&D Formula</button>
        </div>
      </div>

      <div className="rd-formulas-table-wrapper">
        <table className="rd-formulas-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Cost/lb</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 ? (
              <tr>
                <td colSpan={5} className="rd-formulas-empty">No R&D formulas yet. Add one to track formula costs before commercialization.</td>
              </tr>
            ) : (
              list.map((rd) => (
                <tr key={rd.id}>
                  <td><strong>{rd.name}</strong></td>
                  <td><span className={`rd-status rd-status-${rd.status}`}>{rd.status}</span></td>
                  <td>{rd.total_cost_per_lb != null ? `$${rd.total_cost_per_lb.toFixed(2)}` : '—'}</td>
                  <td>{rd.updated_at ? formatAppDate(rd.updated_at) : '—'}</td>
                  <td>
                    <button type="button" onClick={() => openEdit(rd.id)} className="rd-btn rd-btn-edit">Edit</button>
                    <button type="button" onClick={() => handleDelete(rd.id)} className="rd-btn rd-btn-delete">Delete</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="rd-formula-modal-overlay" onClick={closeForm}>
          <div className="rd-formula-modal" onClick={(e) => e.stopPropagation()}>
            <div className="rd-formula-modal-header">
              <h3>{editingId ? 'Edit' : 'Add'} R&D Formula</h3>
              <button type="button" onClick={closeForm} className="rd-formula-modal-close">×</button>
            </div>
            <form onSubmit={handleSubmit} className="rd-formula-form">
              <div className="rd-formula-form-row">
                <label>Product name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Natural Red D1307"
                  required
                />
              </div>
              <div className="rd-formula-form-row">
                <label>Status</label>
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="draft">Draft</option>
                  <option value="approved">Approved</option>
                  <option value="scrapped">Scrapped</option>
                </select>
              </div>
              <div className="rd-formula-form-row">
                <label>Notes</label>
                <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} />
              </div>

              <h4 className="rd-formula-bom-title">Bill of materials</h4>
              <p className="rd-formula-bom-hint">
                Choosing a catalog item fills <strong>Price/lb</strong> from the item&apos;s price (converted to $/lb if priced in kg), or from Cost Master if the item has no price.
              </p>
              <div className="rd-formula-bom-wrap">
                <table className="rd-formula-bom-table">
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Item / description</th>
                      <th>Composition %</th>
                      <th>Price/lb</th>
                      <th>Formula cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {LINE_TYPE_ORDER.map(({ rowId, line_type, sequence }, idx) => {
                      const line = lines[idx]
                      const isLabor = line_type === 'labor'
                      const formulaCost = getFormulaCost(line)
                      return (
                        <tr key={rowId} className={isLabor ? 'rd-bom-row-labor' : ''}>
                          <td className="rd-bom-row-id">{rowId}</td>
                          <td>
                            {isLabor ? (
                              <span className="rd-bom-label">Labor</span>
                            ) : (
                              <>
                                <select
                                  value={line.item_id ?? line.item?.id ?? ''}
                                  onChange={async (e) => {
                                    const v = e.target.value
                                    const itemId = v ? parseInt(v, 10) : null
                                    if (!itemId) {
                                      updateLine(idx, {
                                        item_id: undefined,
                                        item: undefined,
                                        description: '',
                                        price_per_lb: null,
                                      })
                                      return
                                    }
                                    const rowItem = items.find((i) => i.id === itemId)
                                    if (!rowItem) return
                                    let pricePerLb =
                                      pricePerLbFromCatalogItem(rowItem) ??
                                      (await pricePerLbFromCostMasterFallback(rowItem))
                                    updateLine(idx, {
                                      item_id: itemId,
                                      item: { id: rowItem.id, sku: rowItem.sku, name: rowItem.name },
                                      description: `${rowItem.sku} - ${rowItem.name}`,
                                      price_per_lb: pricePerLb,
                                    })
                                  }}
                                  className="rd-bom-item-select"
                                >
                                  <option value="">Select or type below</option>
                                  {items.map((i) => (
                                    <option key={i.id} value={i.id}>{i.sku} - {i.name}</option>
                                  ))}
                                </select>
                                <input
                                  type="text"
                                  value={line.description}
                                  onChange={(e) => updateLine(idx, { description: e.target.value })}
                                  placeholder="Description if no item"
                                  className="rd-bom-desc"
                                />
                              </>
                            )}
                          </td>
                          <td>
                            {!isLabor && (
                              <input
                                type="number"
                                step="0.01"
                                min={0}
                                max={100}
                                value={line.composition_pct ?? ''}
                                onChange={(e) => updateLine(idx, { composition_pct: e.target.value === '' ? null : parseFloat(e.target.value) })}
                                className="rd-bom-pct"
                              />
                            )}
                          </td>
                          <td>
                            {!isLabor ? (
                              <input
                                type="number"
                                step="0.01"
                                min={0}
                                value={line.price_per_lb ?? ''}
                                onChange={(e) => updateLine(idx, { price_per_lb: e.target.value === '' ? null : parseFloat(e.target.value) })}
                                className="rd-bom-price"
                              />
                            ) : (
                              <span className="rd-bom-label">—</span>
                            )}
                          </td>
                          <td className="rd-bom-formula-cost">
                            {isLabor ? (
                              <input
                                type="number"
                                step="0.01"
                                min={0}
                                value={line.labor_flat_amount ?? ''}
                                onChange={(e) => updateLine(idx, { labor_flat_amount: e.target.value === '' ? null : parseFloat(e.target.value) })}
                                className="rd-bom-labor"
                              />
                            ) : (
                              formulaCost != null ? `$${formulaCost.toFixed(2)}` : '—'
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4} className="rd-bom-total-label">Cost/lb (total)</td>
                      <td className="rd-bom-total-value">${totalCost.toFixed(2)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              <div className="rd-formula-form-actions">
                <button type="button" onClick={closeForm} className="btn btn-secondary">Cancel</button>
                <button type="submit" className="btn btn-primary">{editingId ? 'Update' : 'Create'} R&D Formula</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default RDFormulasList
