import React, { useState, useEffect, useCallback } from 'react'
import {
  getCostMasters,
  getLotCostProfile,
  getCostMasterActuals,
  type LotCostProfileResponse,
  type LotCostProfileRow,
} from '../../api/costMaster'
import { formatNumber } from '../../utils/formatNumber'
import { formatAppDate } from '../../utils/appDateFormat'
import './RawMaterialLotCosts.css'

interface CostMasterRow {
  id: number
  vendor_material: string
  wwi_product_code?: string
  vendor?: string
  landed_cost_per_kg?: number
  landed_cost_per_lb?: number
}

function RawMaterialLotCosts() {
  const [rows, setRows] = useState<CostMasterRow[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [profileCache, setProfileCache] = useState<Record<number, LotCostProfileResponse>>({})
  const [loadingProfile, setLoadingProfile] = useState<number | null>(null)
  const [actuals, setActuals] = useState<Record<number, { comparison?: string; shipments_count?: number }>>({})
  const [unit, setUnit] = useState<'kg' | 'lb'>('lb')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getCostMasters({ commercialRaw: true })
      const list = Array.isArray(data) ? data : []
      setRows(list)
      const ids = list.map((r: CostMasterRow) => r.id)
      try {
        const a = await getCostMasterActuals(ids.length ? ids : undefined)
        setActuals(a || {})
      } catch {
        setActuals({})
      }
    } catch (e) {
      console.error(e)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const toggleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null)
      return
    }
    setExpandedId(id)
    if (profileCache[id]) return
    setLoadingProfile(id)
    try {
      const p = await getLotCostProfile(id)
      setProfileCache((prev) => ({ ...prev, [id]: p }))
    } catch (e) {
      console.error(e)
      setProfileCache((prev) => ({
        ...prev,
        [id]: {
          cost_master_id: id,
          wwi_product_code: null,
          vendor: null,
          lots: [],
          message: 'Failed to load lot profile.',
        },
      }))
    } finally {
      setLoadingProfile(null)
    }
  }

  const filtered = rows.filter(
    (r) =>
      !search ||
      r.vendor_material.toLowerCase().includes(search.toLowerCase()) ||
      (r.wwi_product_code && r.wwi_product_code.toLowerCase().includes(search.toLowerCase())) ||
      (r.vendor && r.vendor.toLowerCase().includes(search.toLowerCase()))
  )

  const estDisplay = (cm: CostMasterRow) => {
    const v = unit === 'kg' ? cm.landed_cost_per_kg : cm.landed_cost_per_lb
    return v != null ? `$${formatNumber(v, 4)}/${unit}` : '—'
  }

  const unitActual = (row: { actual_landed_per_kg: number | null; actual_landed_per_lb: number | null }) => {
    const v = unit === 'kg' ? row.actual_landed_per_kg : row.actual_landed_per_lb
    return v != null ? `$${formatNumber(v, 4)}/${unit}` : '—'
  }

  const unitEst = (p: LotCostProfileResponse) => {
    const v = unit === 'kg' ? p.estimate_landed_per_kg : p.estimate_landed_per_lb
    return v != null ? `$${formatNumber(v, 4)}/${unit}` : '—'
  }

  const varDisplay = (row: { variance_per_kg: number | null }) => {
    if (row.variance_per_kg == null) return '—'
    const v = unit === 'kg' ? row.variance_per_kg : row.variance_per_kg / 2.20462
    const sign = v > 0 ? '+' : ''
    return `${sign}$${formatNumber(v, 4)}/${unit}`
  }

  const fmtUsd = (n: number | null | undefined) =>
    n != null && Number.isFinite(n) ? `$${formatNumber(n, 2)}` : '—'

  const mfdShort = (row: LotCostProfileRow) => {
    const m = row.allocated_material_usd
    const f = row.allocated_freight_usd
    const d = row.allocated_duty_usd
    if (m == null && f == null && d == null) return '—'
    return `${fmtUsd(m ?? 0)}/${fmtUsd(f ?? 0)}/${fmtUsd(d ?? 0)}`
  }

  if (loading) {
    return <div className="rm-lot-costs loading">Loading commercial raw materials…</div>
  }

  return (
    <div className="rm-lot-costs">
      <div className="rm-lot-costs-header">
        <div>
          <h2>Raw material — actual lot cost vs estimate</h2>
          <p className="rm-lot-costs-lede">
            <strong>Estimate</strong> is the landed cost on the Cost Master row. <strong>Actual</strong> is built from{' '}
            <strong>Accounts Payable</strong> lines linked to the lot&apos;s PO (vendor invoice = material, separate
            freight and duty/broker/CBP bills with the same PO), plus optional <strong>lot freight</strong> and Cost
            Master <strong>cert</strong> per kg. Totals are allocated to each lot: material by SKU line and received qty,
            freight and duty by weight on the PO. <strong>Payments</strong> on AP do not change these numbers—the
            invoice amounts do.
          </p>
        </div>
        <div className="rm-lot-costs-controls">
          <div className="rm-lot-costs-unit-toggle">
            <button type="button" className={unit === 'lb' ? 'active' : ''} onClick={() => setUnit('lb')}>
              per lb
            </button>
            <button type="button" className={unit === 'kg' ? 'active' : ''} onClick={() => setUnit('kg')}>
              per kg
            </button>
          </div>
          <input
            type="search"
            placeholder="Search material, SKU, vendor…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rm-lot-costs-search"
          />
          <button type="button" className="rm-lot-costs-refresh" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="rm-lot-costs-empty">
          No Cost Master rows linked to a raw material Item (same WWI product code). Add or align Cost Master SKUs with
          Items, or use the Cost Master List for all materials.
        </p>
      ) : (
        <div className="rm-lot-costs-table-wrap">
          <table className="rm-lot-costs-table">
            <thead>
              <tr>
                <th className="col-expand" />
                <th>Vendor material</th>
                <th>WWI code</th>
                <th>Vendor</th>
                <th>Estimate (Cost Master)</th>
                <th>AP shipment avg</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((cm) => {
                const act = actuals[cm.id]
                const isOpen = expandedId === cm.id
                const profile = profileCache[cm.id]
                return (
                  <React.Fragment key={cm.id}>
                    <tr className="rm-lot-costs-master-row">
                      <td>
                        <button
                          type="button"
                          className="rm-lot-costs-expand"
                          onClick={() => toggleExpand(cm.id)}
                          aria-expanded={isOpen}
                        >
                          {isOpen ? '▼' : '▶'}
                        </button>
                      </td>
                      <td>{cm.vendor_material}</td>
                      <td>{cm.wwi_product_code || '—'}</td>
                      <td>{cm.vendor || '—'}</td>
                      <td>{estDisplay(cm)}</td>
                      <td>
                        {act && act.shipments_count ? (
                          <span
                            className={`rm-lot-costs-ap-badge rm-lot-costs-ap-${act.comparison || 'ok'}`}
                            title="Aggregate AP vs estimate (same as Cost Master list)"
                          >
                            {act.shipments_count} shipm. · {act.comparison === 'over' ? 'over' : act.comparison === 'under' ? 'under' : 'ok'}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="rm-lot-costs-detail-row">
                        <td colSpan={6}>
                          {loadingProfile === cm.id && <div className="rm-lot-costs-profile-loading">Loading lots…</div>}
                          {profile && (
                            <div className="rm-lot-costs-profile">
                              {profile.message && <p className="rm-lot-costs-msg">{profile.message}</p>}
                              {profile.lots.length === 0 && !profile.message && (
                                <p className="rm-lot-costs-msg">No inventory lots for this SKU yet.</p>
                              )}
                              {profile.lots.length > 0 && (
                                <table className="rm-lot-costs-lot-table">
                                  <thead>
                                    <tr>
                                      <th>Lot #</th>
                                      <th>PO</th>
                                      <th>Received</th>
                                      <th>Qty</th>
                                      <th>PO price</th>
                                      <th title="Allocated material + freight + duty + lot freight + cert">Total $</th>
                                      <th title="Material / Freight / Duty (allocated)">M / F / D</th>
                                      <th>Actual ({unit})</th>
                                      <th title="Total ÷ received qty in native UOM">Actual / UoM</th>
                                      <th>Estimate</th>
                                      <th>Variance</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {profile.lots.map((lot) => (
                                      <tr key={lot.lot_id}>
                                        <td>{lot.lot_number || lot.lot_id}</td>
                                        <td>{lot.po_number || '—'}</td>
                                        <td>
                                          {lot.received_date
                                            ? formatAppDate(lot.received_date)
                                            : '—'}
                                        </td>
                                        <td>
                                          {formatNumber(lot.quantity_received, 0)} {lot.item_uom}
                                        </td>
                                        <td>
                                          {lot.po_unit_price != null
                                            ? `$${formatNumber(lot.po_unit_price, 4)}/${lot.po_price_uom || ''}`
                                            : '—'}
                                        </td>
                                        <td>{fmtUsd(lot.total_actual_cost_usd)}</td>
                                        <td className="rm-lot-costs-mfd" title="Material / Freight / Duty (USD)">
                                          {mfdShort(lot)}
                                        </td>
                                        <td className={`rm-lot-costs-cmp-${lot.comparison}`}>{unitActual(lot)}</td>
                                        <td>
                                          {lot.actual_landed_per_uom != null
                                            ? `$${formatNumber(lot.actual_landed_per_uom, 4)}/${lot.item_uom}`
                                            : '—'}
                                        </td>
                                        <td>{unitEst(profile)}</td>
                                        <td className={`rm-lot-costs-cmp-${lot.comparison}`}>{varDisplay(lot)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              )}
                              {profile.methodology && (
                                <p className="rm-lot-costs-footnote">{profile.methodology}</p>
                              )}
                              <p className="rm-lot-costs-footnote">
                                In Finance → Accounts Payable, link each bill to the PO and set <strong>Cost category</strong>{' '}
                                (material vs freight vs duty/tax). Legacy rows count the invoice total as material and still
                                honor freight/tariff columns on each line.
                              </p>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default RawMaterialLotCosts
