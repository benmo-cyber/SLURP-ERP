import React, { useState, useEffect, useRef } from 'react'
import {
  getInventoryDetails,
  getLotsBySkuVendor,
  updateLot,
  regenerateLotCoa,
  putLotOnHold,
  releaseLotFromHold,
  reconcileLot,
} from '../../api/inventory'
import { coaReleasePreview, type CoaReleasePreview } from '../../api/coa'
import ReleaseFromHoldCoaModal from './ReleaseFromHoldCoaModal'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import { formatNumber, formatNumberFlexible } from '../../utils/formatNumber'
import { formatQuantityForDisplay, normalizeEaQuantity } from '../../utils/massQuantity'
import { formatAppDate, formatAppDateTimeShort } from '../../utils/appDateFormat'
import { lotAvailableForUse } from '../../utils/lotQuantities'
import './InventoryTable.css'
import { SkuFamilyWarningIcon, type SkuFamilyWarning } from './SkuFamilyWarningIcon'

interface InventoryDetail {
  id: string | number
  item_id: number
  item_sku: string
  description: string
  vendor?: string
  pack_size?: number
  pack_size_unit: string
  total_quantity: number
  allocated_to_sales: number
  allocated_to_production: number
  on_hold: number
  on_order: number
  available: number
  quantity_remaining: number
  lot_count?: number
  item_type?: string
  product_category?: string
  level?: 'sku' | 'vendor'  // Hierarchy level
  vendor_count?: number  // Number of vendors for SKU
  vendors?: InventoryDetail[]  // Nested vendor entries
  pack_sizes?: { pack_size: number; pack_size_unit: string }[]
  sku_parent_code?: string
  sku_pack_suffix?: string
  sku_family_warnings?: SkuFamilyWarning[]
}

type InventorySection =
  | { type: 'family'; parentCode: string; members: InventoryDetail[] }
  | { type: 'single'; detail: InventoryDetail }

function shouldShowInventoryFamily(members: InventoryDetail[]): boolean {
  if (members.length > 1) return true
  if (members.length === 1) {
    const m = members[0]
    return !!(m.sku_pack_suffix && String(m.sku_pack_suffix).trim())
  }
  return false
}

function sortFamilySkuMembers(members: InventoryDetail[]): InventoryDetail[] {
  const suf = (d: InventoryDetail) => (d.sku_pack_suffix || '').trim()
  const pc = (d: InventoryDetail) => (d.sku_parent_code || '').trim().toUpperCase()
  return [...members].sort((a, b) => {
    const aMaster = !suf(a) || (a.item_sku || '').toUpperCase() === pc(a)
    const bMaster = !suf(b) || (b.item_sku || '').toUpperCase() === pc(b)
    if (aMaster !== bMaster) return aMaster ? -1 : 1
    return (a.item_sku || '').localeCompare(b.item_sku || '')
  })
}

function buildInventorySections(skuMasterRows: InventoryDetail[]): InventorySection[] {
  const masters = skuMasterRows.filter((d) => d.level === 'sku')
  const byParent = new Map<string, InventoryDetail[]>()
  for (const d of masters) {
    const p = (d.sku_parent_code || '').trim()
    if (p) {
      if (!byParent.has(p)) byParent.set(p, [])
      byParent.get(p)!.push(d)
    }
  }
  const emittedFamilies = new Set<string>()
  const sections: InventorySection[] = []
  for (const d of masters) {
    const p = (d.sku_parent_code || '').trim()
    if (!p) {
      sections.push({ type: 'single', detail: d })
      continue
    }
    const members = byParent.get(p)!
    if (!shouldShowInventoryFamily(members)) {
      sections.push({ type: 'single', detail: d })
      continue
    }
    if (emittedFamilies.has(p)) continue
    emittedFamilies.add(p)
    sections.push({ type: 'family', parentCode: p, members: sortFamilySkuMembers(members) })
  }
  return sections
}

/** Prefer master row (no pack suffix / SKU equals parent code) for the family label; else first row. */
function familyParentDescriptionLabel(parentCode: string, members: InventoryDetail[]): string {
  const pc = parentCode.trim().toUpperCase()
  const master = members.find(
    (m) =>
      !(m.sku_pack_suffix || '').trim() || (m.item_sku || '').trim().toUpperCase() === pc
  )
  const base = (master || members[0]).description?.trim() || parentCode
  const n = members.length
  return `${base} - ${n} ${n === 1 ? 'sku' : 'skus'}`
}

function aggregateFamilyInventoryRow(parentCode: string, members: InventoryDetail[]): InventoryDetail {
  const first = members[0]
  let total_quantity = 0
  let allocated_to_sales = 0
  let allocated_to_production = 0
  let on_hold = 0
  let on_order = 0
  let available = 0
  let quantity_remaining = 0
  let lot_count = 0
  let vendor_count = 0
  for (const m of members) {
    total_quantity += m.total_quantity ?? 0
    allocated_to_sales += m.allocated_to_sales ?? 0
    allocated_to_production += m.allocated_to_production ?? 0
    on_hold += m.on_hold ?? 0
    on_order += m.on_order ?? 0
    available += m.available ?? 0
    quantity_remaining += m.quantity_remaining ?? 0
    lot_count += m.lot_count ?? 0
    vendor_count += m.vendor_count ?? 0
  }
  return {
    ...first,
    id: `FAMILY_${parentCode}`,
    item_sku: parentCode,
    description: familyParentDescriptionLabel(parentCode, members),
    item_id: first.item_id,
    total_quantity,
    allocated_to_sales,
    allocated_to_production,
    on_hold,
    on_order,
    available,
    quantity_remaining,
    lot_count,
    vendor_count,
    level: 'sku',
    vendors: [],
    sku_parent_code: parentCode,
    sku_pack_suffix: '',
    sku_family_warnings: [],
  }
}

interface Lot {
  id: number
  lot_number: string
  vendor_lot_number?: string
  po_number?: string
  po_tracking_number?: string
  po_carrier?: string
  quantity: number
  quantity_remaining: number
  quantity_available_for_use?: number
  quantity_on_hold?: number
  received_date: string
  manufacture_date?: string
  expiration_date?: string
  status: string
  committed_to_sales_qty?: number
  committed_to_production_qty?: number
  pack_size_obj?: {
    id: number
    pack_size: number
    pack_size_unit: string
    description?: string
  }
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure: string
    item_type?: string
    pack_sizes?: { pack_size: number; pack_size_unit: string }[]
    default_pack_size?: { pack_size: number; pack_size_unit: string } | null
  }
  depleted_at?: string | null
  coa_pdf_url?: string | null
  coa_issued?: boolean
}

type DepletedLotTableProps = {
  lots: Lot[]
  convertQuantity: (quantity: number, unit: string) => string
  getDisplayUnit: (unit: string) => string
  formatNumberFlexible: (n: number, min?: number, max?: number) => string
}

/** Read-only rows for zero on-hand lots (Deeper…). */
function DepletedLotTable({ lots, convertQuantity, getDisplayUnit, formatNumberFlexible }: DepletedLotTableProps) {
  return (
    <table className="lot-table lot-table-depleted">
      <thead>
        <tr>
          <th>Vendor Lot #</th>
          <th>Internal Lot #</th>
          <th>PO Number</th>
          <th>Tracking</th>
          <th>Pack Size</th>
          <th>Received Date</th>
          <th>Mfg Date</th>
          <th>Expiration Date</th>
          <th title="Original received at check-in">Received</th>
          <th>Available</th>
          <th>On Hold</th>
          <th>Status</th>
          <th>Depleted</th>
          <th>Committed</th>
        </tr>
      </thead>
      <tbody>
        {lots.map((lot) => {
          const lotUnit = lot.item.unit_of_measure
          const receivedDate = formatAppDate(lot.received_date)
          const mfgDate = lot.manufacture_date ? formatAppDate(lot.manufacture_date) : 'N/A'
          const expDate = lot.expiration_date ? formatAppDate(lot.expiration_date) : 'N/A'
          const depletedLabel = lot.depleted_at
            ? formatAppDateTimeShort(lot.depleted_at)
            : '—'
          const packSizeDisplay = lot.pack_size_obj
            ? `${lot.pack_size_obj.pack_size} ${lot.pack_size_obj.pack_size_unit}${
                lot.pack_size_obj.description ? ` (${lot.pack_size_obj.description})` : ''
              }`
            : '-'
          return (
            <tr key={lot.id} className="lot-row-depleted">
              <td>{lot.vendor_lot_number || '-'}</td>
              <td>{lot.lot_number || '-'}</td>
              <td>{lot.po_number || '-'}</td>
              <td>
                {lot.po_tracking_number ? (
                  <span>
                    {lot.po_tracking_number}
                    {lot.po_carrier && ` (${lot.po_carrier})`}
                  </span>
                ) : (
                  '-'
                )}
              </td>
              <td>{packSizeDisplay}</td>
              <td>{receivedDate}</td>
              <td>{mfgDate}</td>
              <td>{expDate}</td>
              <td className="lot-table-col-qty">
                {lotUnit !== 'ea' ? (
                  <>
                    {convertQuantity(lot.quantity, lotUnit)} {getDisplayUnit(lotUnit)}
                  </>
                ) : (
                  <>{formatNumberFlexible(lot.quantity, 0, 5)} ea</>
                )}
              </td>
              <td className="lot-table-col-qty">
                {lotUnit !== 'ea' ? (
                  <>
                    {convertQuantity(lotAvailableForUse(lot), lotUnit)} {getDisplayUnit(lotUnit)}
                  </>
                ) : (
                  <>{formatNumberFlexible(lotAvailableForUse(lot), 0, 5)} ea</>
                )}
              </td>
              <td className="lot-table-col-qty">
                {lotUnit !== 'ea' ? (
                  <>
                    {convertQuantity(lot.quantity_on_hold ?? 0, lotUnit)} {getDisplayUnit(lotUnit)}
                  </>
                ) : (
                  <>{formatNumberFlexible(lot.quantity_on_hold ?? 0, 0, 5)} ea</>
                )}
              </td>
              <td>
                <span className={`status-badge status-${lot.status}`}>{lot.status}</span>
              </td>
              <td className="lot-table-col-qty" title="When on-hand reached zero">
                {depletedLabel}
              </td>
              <td className="lot-table-col-qty lot-table-col-committed">
                <span className="committed-badge not-committed">—</span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function InventoryTable() {
  const [inventoryDetails, setInventoryDetails] = useState<InventoryDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  const [inventoryTable, setInventoryTable] = useState<'finished_good' | 'raw_material' | 'indirect_material'>('finished_good')
  const [fpsLinks, setFpsLinks] = useState<Map<number, number>>(new Map())
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  /** Expanded material-family parent rows (parent SKU code). */
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set())
  const [lotDetails, setLotDetails] = useState<Map<string, Lot[]>>(new Map())
  const [loadingLots, setLoadingLots] = useState<Set<string>>(new Set())
  const [deeperLotDetails, setDeeperLotDetails] = useState<Map<string, Lot[]>>(new Map())
  const [deeperSectionOpen, setDeeperSectionOpen] = useState<Set<string>>(new Set())
  const [loadingDeeperLots, setLoadingDeeperLots] = useState<Set<string>>(new Set())
  const [editingLot, setEditingLot] = useState<{
    lotId: number
    field: 'vendor_lot_number' | 'lot_number' | 'expiration_date' | 'manufacture_date'
  } | null>(null)
  const [editValue, setEditValue] = useState<string>('')
  const [releaseCoaModal, setReleaseCoaModal] = useState<{
    lotId: number
    lotLabel: string
    releaseQty: number
    preview: CoaReleasePreview
    vendorRowKey: string
  } | null>(null)
  const [sortConfig, setSortConfig] = useState<{key: 'description' | 'vendor' | null, direction: 'asc' | 'desc'}>({ key: null, direction: 'asc' })
  const loadInFlightRef = useRef(false)
  const fpsLoadKeyRef = useRef('')

  useEffect(() => {
    loadData()
  }, [inventoryTable])

  useEffect(() => {
    setExpandedRows(new Set())
    setExpandedFamilies(new Set())
    setLotDetails(new Map())
    setDeeperLotDetails(new Map())
    setDeeperSectionOpen(new Set())
    setLoadingDeeperLots(new Set())
  }, [inventoryTable])

  const handleSort = (key: 'description' | 'vendor') => {
    setSortConfig(prevConfig => ({
      key,
      direction: prevConfig.key === key && prevConfig.direction === 'asc' ? 'desc' : 'asc'
    }))
  }

  const sortedInventoryDetails = [...inventoryDetails].sort((a, b) => {
    if (!sortConfig.key) return 0
    
    let aValue = ''
    let bValue = ''
    
    if (sortConfig.key === 'description') {
      aValue = a.description?.toLowerCase() || ''
      bValue = b.description?.toLowerCase() || ''
    } else if (sortConfig.key === 'vendor') {
      aValue = (a.vendor || 'zzz').toLowerCase()  // 'zzz' for "All Vendors" to sort last
      bValue = (b.vendor || 'zzz').toLowerCase()
    }
    
    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  })

  const inventorySections = buildInventorySections(
    sortedInventoryDetails.filter((d) => d.level === 'sku')
  )

  useEffect(() => {
    // Load FPS links for finished goods only when the finished-good item IDs actually change.
    const key = inventoryDetails
      .filter((d) => d.item_type === 'finished_good' && d.level === 'sku')
      .map((d) => String(d.item_id))
      .sort()
      .join(',')
    if (!key || key === fpsLoadKeyRef.current) return
    fpsLoadKeyRef.current = key
    loadFpsLinks()
  }, [inventoryDetails])

  const loadData = async () => {
    if (loadInFlightRef.current) return
    loadInFlightRef.current = true
    try {
      setLoading(true)
      console.log('Loading inventory details...')
      const data = await getInventoryDetails(inventoryTable)
      console.log('Inventory data received:', data)
      console.log('Number of entries:', Array.isArray(data) ? data.length : 'Not an array')
      if (Array.isArray(data) && data.length > 0) {
        console.log('First entry:', data[0])
      }
      setInventoryDetails(Array.isArray(data) ? data : [])
    } catch (error: any) {
      console.error('Failed to load inventory:', error)
      console.error('Error response:', error.response?.data)
      console.error('Error status:', error.response?.status)
      // For 500 errors, just set empty data (server will handle gracefully)
      if (error.response?.status === 500) {
        console.error('Server error loading inventory, returning empty data')
        setInventoryDetails([])
      } else {
        // Only show alert for non-500 errors
        alert(`Failed to load inventory data: ${error.message || 'Unknown error'}. Make sure the backend server is running on http://localhost:8000`)
      }
    } finally {
      loadInFlightRef.current = false
      setLoading(false)
    }
  }

  const loadFpsLinks = async () => {
    // Get unique item IDs for finished goods (from master SKU rows)
    const finishedGoodItemIds = new Set<number>()
    inventoryDetails.forEach(detail => {
      if (detail.item_type === 'finished_good' && detail.level === 'sku') {
        finishedGoodItemIds.add(detail.item_id)
      }
    })

    // Load FPS for each finished good
    const links = new Map<number, number>()
    for (const itemId of finishedGoodItemIds) {
      try {
        const fps = await getFinishedProductSpecification(itemId)
        if (fps && fps.id) {
          links.set(itemId, fps.id)
        }
      } catch (error) {
        // FPS doesn't exist for this item, that's okay
      }
    }
    setFpsLinks(links)
  }

  /** Convert stored qty to selected display unit; normalize float drift (3149.96 → 3150). */
  const convertQuantity = (quantity: number, unit: string) =>
    formatQuantityForDisplay(quantity, unit, unitDisplay)

  const getDisplayUnit = (unit: string) => {
    if (unit === 'ea') return 'ea'
    return unitDisplay
  }

  /** Inventory is stored in item UOM (ea = each bag/unit — no roll×pack conversion). */
  const formatInventoryMeasure = (_detail: InventoryDetail, value: number, unit: string) => {
    if (unit !== 'ea') return formatQuantityForDisplay(value, unit, unitDisplay)
    return formatNumber(normalizeEaQuantity(value), 0)
  }

  const inventoryMeasureUnit = (_detail: InventoryDetail, unit: string) => getDisplayUnit(unit)

  const formatItemType = (itemType?: string) => {
    if (!itemType) return '-'
    const map: Record<string, string> = {
      raw_material: 'Raw Material',
      distributed_item: 'Distributed',
      finished_good: 'Finished Good',
      indirect_material: 'Indirect',
    }
    return map[itemType] || itemType.replace(/_/g, ' ')
  }

  const formatProductCategory = (cat?: string | null) => {
    if (!cat) return '—'
    const map: Record<string, string> = {
      natural_colors: 'Natural Colors',
      synthetic_colors: 'Synthetic Colors',
      antioxidants: 'Antioxidants',
      other: 'Other',
    }
    return map[cat] || cat.replace(/_/g, ' ')
  }

  const handleDeeperToggle = async (rowKey: string, detail: InventoryDetail) => {
    if (deeperSectionOpen.has(rowKey)) {
      setDeeperSectionOpen((prev) => {
        const next = new Set(prev)
        next.delete(rowKey)
        return next
      })
      return
    }
    setDeeperSectionOpen((prev) => new Set(prev).add(rowKey))
    if (deeperLotDetails.has(rowKey)) return
    setLoadingDeeperLots((prev) => new Set(prev).add(rowKey))
    try {
      const rows = await getLotsBySkuVendor(detail.item_sku, detail.vendor, inventoryTable, {
        deeper: true,
      })
      setDeeperLotDetails((prev) => new Map(prev).set(rowKey, Array.isArray(rows) ? rows : []))
    } catch (e) {
      console.error('Failed to load depleted lots:', e)
      setDeeperLotDetails((prev) => new Map(prev).set(rowKey, []))
    } finally {
      setLoadingDeeperLots((prev) => {
        const next = new Set(prev)
        next.delete(rowKey)
        return next
      })
    }
  }

  const toggleSkuExpansion = (sku: string) => {
    const rowKey = `SKU_${sku}`
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(rowKey)) next.delete(rowKey)
      else next.add(rowKey)
      return next
    })
  }

  const toggleFamilyExpansion = (parentCode: string) => {
    setExpandedFamilies((prev) => {
      const next = new Set(prev)
      if (next.has(parentCode)) next.delete(parentCode)
      else next.add(parentCode)
      return next
    })
  }

  const toggleVendorExpansion = async (detail: InventoryDetail) => {
    const rowKey = `${detail.item_sku}_${detail.vendor}`
    if (expandedRows.has(rowKey)) {
      setExpandedRows((prev) => {
        const next = new Set(prev)
        next.delete(rowKey)
        return next
      })
      setDeeperSectionOpen((prev) => {
        const next = new Set(prev)
        next.delete(rowKey)
        return next
      })
      return
    }
    setExpandedRows((prev) => new Set(prev).add(rowKey))
    if (!lotDetails.has(rowKey)) {
      setLoadingLots(new Set([...loadingLots, rowKey]))
      try {
        const lots = await getLotsBySkuVendor(detail.item_sku, detail.vendor, inventoryTable)
        setLotDetails((prev) => new Map(prev).set(rowKey, lots))
      } catch (error) {
        console.error('Failed to load lot details:', error)
      } finally {
        setLoadingLots((prev) => {
          const next = new Set(prev)
          next.delete(rowKey)
          return next
        })
      }
    }
  }

  /** PO/on-order is a raw-planning signal; hide on Finished Goods to avoid duplicate/confusing context. */
  const showOnOrderColumn = inventoryTable !== 'finished_good'
  const inventoryMainColSpan = showOnOrderColumn ? 12 : 11

  const renderSkuMasterSection = (detail: InventoryDetail, opts?: { underFamily?: boolean }) => {
    if (detail.level !== 'sku') return null
    const unit = detail.pack_size_unit
    const displayAllocSales = formatInventoryMeasure(detail, detail.allocated_to_sales, unit)
    const displayAllocProd = formatInventoryMeasure(detail, detail.allocated_to_production, unit)
    const displayOnHold = formatInventoryMeasure(detail, detail.on_hold, unit)
    const displayOnOrder = showOnOrderColumn ? formatInventoryMeasure(detail, detail.on_order, unit) : ''
    const displayAvailable = formatInventoryMeasure(detail, detail.available, unit)
    const displayUnit = inventoryMeasureUnit(detail, unit)

    const hasFps = fpsLinks.has(detail.item_id) && detail.item_type === 'finished_good'
    const fpsId = fpsLinks.get(detail.item_id)

    const vendors = detail.vendors || []
    const isSkuExpanded = expandedRows.has(`SKU_${detail.item_sku}`)

    return (
      <React.Fragment key={detail.id}>
        <tr
          className={`sku-master-row ${detail.on_hold > 0 ? 'on-hold' : ''} ${
            opts?.underFamily ? 'inv-sku-under-family' : ''
          }`}
        >
          <td>
            <div className="sku-cell">
              {vendors.length > 0 && (
                <button
                  type="button"
                  className="expand-btn"
                  onClick={() => toggleSkuExpansion(detail.item_sku)}
                  title={isSkuExpanded ? 'Collapse vendor breakdown' : 'Expand vendor breakdown'}
                  aria-expanded={isSkuExpanded}
                >
                  {isSkuExpanded ? '▼' : '▶'}
                </button>
              )}
              <span className="sku-master-label">{detail.item_sku}</span>
              <SkuFamilyWarningIcon warnings={detail.sku_family_warnings} />
              {vendors.length > 1 && <span className="vendor-count-badge">{vendors.length}</span>}
            </div>
          </td>
          <td>
            {hasFps && fpsId ? (
              <a
                href={getFpsPdfUrl(fpsId)}
                target="_blank"
                rel="noopener noreferrer"
                className="fps-link"
                onClick={(e) => e.stopPropagation()}
              >
                {detail.description}
              </a>
            ) : (
              detail.description
            )}
          </td>
          <td>
            <span className={`inventory-type-badge inventory-type-badge--${detail.item_type || 'unknown'}`}>
              {formatItemType(detail.item_type)}
            </span>
          </td>
          <td>
            <span className={`inventory-category-badge inventory-category-badge--${detail.product_category || 'none'}`}>
              {formatProductCategory(detail.product_category)}
            </span>
          </td>
          <td>All Vendors</td>
          <td>{detail.sku_pack_suffix ? <span title="Pack code from SKU">{detail.sku_pack_suffix}</span> : '-'}</td>
          <td className={detail.available > 0 ? 'available' : 'unavailable'}>
            {displayAvailable} {displayUnit}
          </td>
          {showOnOrderColumn && (
            <td className={detail.on_order > 0 ? 'on-order' : ''}>
              {displayOnOrder} {displayUnit}
            </td>
          )}
          <td>{displayAllocSales} {displayUnit}</td>
          <td>{displayAllocProd} {displayUnit}</td>
          <td>{displayOnHold} {displayUnit}</td>
          <td>{detail.lot_count || 0}</td>
        </tr>
        {isSkuExpanded &&
          vendors.map((vendorDetail) => {
                        const vendorUnit = vendorDetail.pack_size_unit
                        const vendorDisplayAllocSales = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.allocated_to_sales, vendorUnit) : formatNumber(vendorDetail.allocated_to_sales, 0)
                        const vendorDisplayAllocProd = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.allocated_to_production, vendorUnit) : formatNumber(vendorDetail.allocated_to_production, 0)
                        const vendorDisplayOnHold = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.on_hold, vendorUnit) : formatNumber(vendorDetail.on_hold, 0)
                        const vendorDisplayOnOrder = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.on_order, vendorUnit) : formatNumber(vendorDetail.on_order, 0)
                        const vendorDisplayAvailable = vendorUnit !== 'ea' ? convertQuantity(vendorDetail.available, vendorUnit) : formatNumber(vendorDetail.available, 0)
                        const vendorDisplayUnit = getDisplayUnit(vendorUnit)
                        const vendorPackSizeDisplay = vendorDetail.pack_size ? `${vendorDetail.pack_size} ${vendorUnit}` : '-'

                        const vendorRowKey = `${vendorDetail.item_sku}_${vendorDetail.vendor}`
                        const isVendorExpanded = expandedRows.has(vendorRowKey)
                        const vendorLots = lotDetails.get(vendorRowKey) || []
                        const isLoadingVendorLots = loadingLots.has(vendorRowKey)

                        return (
                          <React.Fragment key={vendorDetail.id}>
                            <tr
                              className={`vendor-row ${vendorDetail.on_hold > 0 ? 'on-hold' : ''}`}
                            >
                              <td>
                                <div className="sku-cell">
                                  <span>↳ {vendorDetail.item_sku}</span>
                                  {(vendorDetail.lot_count ?? 0) > 0 && (
                                    <button
                                      type="button"
                                      className="expand-btn"
                                      onClick={() => void toggleVendorExpansion(vendorDetail)}
                                      title={isVendorExpanded ? 'Collapse lot details' : 'Expand lot details'}
                                      aria-expanded={isVendorExpanded}
                                    >
                                      {isVendorExpanded ? '▼' : '▶'}
                                    </button>
                                  )}
                                </div>
                              </td>
                              <td>{vendorDetail.description}</td>
                              <td>
                                <span
                                  className={`inventory-type-badge inventory-type-badge--${vendorDetail.item_type || 'unknown'}`}
                                >
                                  {formatItemType(vendorDetail.item_type)}
                                </span>
                              </td>
                              <td>
                                <span
                                  className={`inventory-category-badge inventory-category-badge--${vendorDetail.product_category || 'none'}`}
                                >
                                  {formatProductCategory(vendorDetail.product_category)}
                                </span>
                              </td>
                              <td>{vendorDetail.vendor}</td>
                              <td>{vendorPackSizeDisplay}</td>
                              <td className={vendorDetail.available > 0 ? 'available' : 'unavailable'}>
                                {vendorDisplayAvailable} {vendorDisplayUnit}
                              </td>
                              {showOnOrderColumn && (
                                <td className={vendorDetail.on_order > 0 ? 'on-order' : ''}>
                                  {vendorDisplayOnOrder} {vendorDisplayUnit}
                                </td>
                              )}
                              <td>{vendorDisplayAllocSales} {vendorDisplayUnit}</td>
                              <td>{vendorDisplayAllocProd} {vendorDisplayUnit}</td>
                              <td>{vendorDisplayOnHold} {vendorDisplayUnit}</td>
                              <td>{vendorDetail.lot_count || 0}</td>
                            </tr>
                            {isVendorExpanded && (
                              <tr className="lot-details-row">
                                <td colSpan={inventoryMainColSpan} className="lot-details-cell">
                                  {isLoadingVendorLots ? (
                                    <div className="loading-lots">Loading lot details...</div>
                                  ) : vendorLots.length === 0 ? (
                                    <div className="no-lots">No lots found</div>
                                  ) : (
                                    <div className="lot-breakdown">
                                      <h4>Lot Breakdown for {vendorDetail.item_sku} - {vendorDetail.vendor}</h4>
                                      <div className="lot-table-scroll">
                                      <table className="lot-table">
                                        <thead>
                                          <tr>
                                            <th>Vendor Lot #</th>
                                            <th>Internal Lot #</th>
                                            <th>PO Number</th>
                                            <th>Tracking</th>
                                            <th>Pack Size</th>
                                            <th>Received Date</th>
                                            <th>Mfg Date</th>
                                            <th>Expiration Date</th>
                                            <th>Quantity</th>
                                            <th>Available</th>
                                            <th>On Hold</th>
                                            <th>Status</th>
                                            <th>Committed</th>
                                            <th>Actions</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {vendorLots.map((lot) => {
                                            const lotUnit = lot.item.unit_of_measure
                                            const displayQty = lotUnit !== 'ea' ? convertQuantity(lot.quantity, lotUnit) : formatNumber(lot.quantity, 0)
                                            const prodCommit = lot.committed_to_production_qty ?? 0
                                            const onHold = lot.quantity_on_hold ?? 0
                                            const availableFromLot = lotAvailableForUse(lot)
                                            const displayRemaining =
                                              lotUnit !== 'ea'
                                                ? convertQuantity(availableFromLot, lotUnit)
                                                : formatNumber(availableFromLot, 0)
                                            const lotDisplayUnit = getDisplayUnit(lotUnit)
                                            const receivedDate = new Date(lot.received_date).toLocaleDateString()
                                            const mfgDate = lot.manufacture_date ? new Date(lot.manufacture_date).toLocaleDateString() : 'N/A'
                                            const expDate = lot.expiration_date ? new Date(lot.expiration_date).toLocaleDateString() : 'N/A'
                                            const packSizeDisplay = lot.pack_size_obj 
                                              ? `${lot.pack_size_obj.pack_size} ${lot.pack_size_obj.pack_size_unit}${lot.pack_size_obj.description ? ` (${lot.pack_size_obj.description})` : ''}`
                                              : '-'
                                            
                                            const isEditingVendorLot = editingLot?.lotId === lot.id && editingLot?.field === 'vendor_lot_number'
                                            const isEditingMfgDate = editingLot?.lotId === lot.id && editingLot?.field === 'manufacture_date'
                                            const isEditingExpDate = editingLot?.lotId === lot.id && editingLot?.field === 'expiration_date'
                                            
                                            const handleFieldClick = (
                                              lotId: number,
                                              field: 'vendor_lot_number' | 'expiration_date' | 'manufacture_date',
                                              currentValue: string
                                            ) => {
                                              setEditingLot({ lotId, field })
                                              if (
                                                (field === 'expiration_date' || field === 'manufacture_date') &&
                                                currentValue !== 'N/A'
                                              ) {
                                                const dateObj = new Date(currentValue)
                                                const year = dateObj.getFullYear()
                                                const month = String(dateObj.getMonth() + 1).padStart(2, '0')
                                                const day = String(dateObj.getDate()).padStart(2, '0')
                                                setEditValue(`${year}-${month}-${day}`)
                                              } else {
                                                setEditValue(currentValue === '-' || currentValue === 'N/A' ? '' : currentValue)
                                              }
                                            }
                                            
                                            const handleFieldSave = async () => {
                                              if (!editingLot) return
                                              
                                              try {
                                                const updateData: any = {}
                                                if (editingLot.field === 'vendor_lot_number') {
                                                  updateData.vendor_lot_number = editValue.trim() || null
                                                } else if (editingLot.field === 'expiration_date') {
                                                  updateData.expiration_date = editValue.trim() || null
                                                  const reason =
                                                    window.prompt(
                                                      'Reason for expiration change (optional, e.g. shelf-life extension):'
                                                    ) ?? ''
                                                  if (reason.trim()) {
                                                    updateData.expiration_change_reason = reason.trim()
                                                  }
                                                } else if (editingLot.field === 'manufacture_date') {
                                                  updateData.manufacture_date = editValue.trim() || null
                                                  const reason =
                                                    window.prompt(
                                                      'Reason for manufacture date change (optional):'
                                                    ) ?? ''
                                                  if (reason.trim()) {
                                                    updateData.manufacture_change_reason = reason.trim()
                                                  }
                                                }

                                                await updateLot(lot.id, updateData)
                                                
                                                // Update local state
                                                const updatedLots = vendorLots.map(l => 
                                                  l.id === lot.id 
                                                    ? { ...l, ...updateData }
                                                    : l
                                                )
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                
                                                setEditingLot(null)
                                                setEditValue('')
                                              } catch (error) {
                                                console.error('Failed to update lot:', error)
                                                alert('Failed to update lot. Please try again.')
                                              }
                                            }
                                            
                                            const handleFieldCancel = () => {
                                              setEditingLot(null)
                                              setEditValue('')
                                            }
                                            
                                            const handleKeyDown = (e: React.KeyboardEvent) => {
                                              if (e.key === 'Enter') {
                                                handleFieldSave()
                                              } else if (e.key === 'Escape') {
                                                handleFieldCancel()
                                              }
                                            }
                                            
                                            const qtyOnHold = lot.quantity_on_hold ?? 0
                                            const handlePutOnHold = async () => {
                                              const raw = window.prompt(
                                                `Put how much on hold? (Max available from this lot.) Unit: ${lotDisplayUnit}`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty <= 0) {
                                                alert('Enter a positive number.')
                                                return
                                              }
                                              try {
                                                const updated = await putLotOnHold(lot.id, qty)
                                                const updatedLots = vendorLots.map(l => l.id === lot.id ? { ...l, ...updated } : l)
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                console.error('Put on hold failed:', err)
                                                alert(err?.response?.data?.error || 'Failed to put on hold.')
                                              }
                                            }
                                            const handleReleaseFromHold = async () => {
                                              const maxRelease = qtyOnHold
                                              if (maxRelease <= 0) return
                                              const raw = window.prompt(
                                                `Release how much from hold? (Max: ${formatNumber(lotUnit !== 'ea' ? convertQuantity(maxRelease, lotUnit) : maxRelease, 2)} ${lotDisplayUnit})`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty <= 0 || qty > maxRelease) {
                                                alert(`Enter a number between 0 and ${maxRelease}.`)
                                                return
                                              }
                                              const releaseErr = (err: any) => {
                                                console.error('Release from hold failed:', err)
                                                const d = err?.response?.data
                                                const msg =
                                                  typeof d?.error === 'string'
                                                    ? d.error
                                                    : Array.isArray(d?.detail)
                                                      ? d.detail.map((x: unknown) => String(x)).join(', ')
                                                      : typeof d?.detail === 'string'
                                                        ? d.detail
                                                        : err?.message || 'Failed to release from hold.'
                                                alert(msg)
                                              }
                                              try {
                                                const preview = await coaReleasePreview(lot.id, qty)
                                                if (preview.coa_required) {
                                                  setReleaseCoaModal({
                                                    lotId: lot.id,
                                                    lotLabel: lot.lot_number || String(lot.id),
                                                    releaseQty: qty,
                                                    preview,
                                                    vendorRowKey,
                                                  })
                                                  return
                                                }
                                                const updated = await releaseLotFromHold(lot.id, qty)
                                                const updatedLots = vendorLots.map((l) =>
                                                  l.id === lot.id ? { ...l, ...updated } : l
                                                )
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                releaseErr(err)
                                              }
                                            }
                                            const handleReconcile = async () => {
                                              const currentRem = lot.quantity_remaining
                                              const raw = window.prompt(
                                                `Admin reconcile: set quantity remaining (physical) for this lot. Current: ${formatNumber(lotUnit !== 'ea' ? convertQuantity(currentRem, lotUnit) : currentRem, 2)} ${lotDisplayUnit}. New value:`
                                              )
                                              if (raw == null) return
                                              const qty = parseFloat(raw)
                                              if (Number.isNaN(qty) || qty < 0) {
                                                alert('Enter a non-negative number.')
                                                return
                                              }
                                              const reason = window.prompt('Reason for reconcile (optional):') || 'Admin reconcile'
                                              const valueInItemUnit = lotUnit === 'ea' ? qty : (unitDisplay === 'kg' && lotUnit === 'lbs' ? qty * 2.20462 : unitDisplay === 'lbs' && lotUnit === 'kg' ? qty / 2.20462 : qty)
                                              try {
                                                const updated = await reconcileLot(lot.id, valueInItemUnit, reason)
                                                const updatedLots = vendorLots.map(l => l.id === lot.id ? { ...l, ...updated } : l)
                                                setLotDetails(new Map([...lotDetails, [vendorRowKey, updatedLots]]))
                                                loadData()
                                              } catch (err: any) {
                                                console.error('Reconcile failed:', err)
                                                alert(err?.response?.data?.error || 'Reconcile failed. Requires staff/superuser.')
                                              }
                                            }
                                            
                                            return (
                                              <tr key={lot.id}>
                                                <td 
                                                  className="editable-cell"
                                                  onClick={() => handleFieldClick(lot.id, 'vendor_lot_number', lot.vendor_lot_number || '-')}
                                                  title="Click to edit vendor lot number"
                                                >
                                                  {isEditingVendorLot ? (
                                                    <input
                                                      type="text"
                                                      value={editValue}
                                                      onChange={(e) => setEditValue(e.target.value)}
                                                      onBlur={handleFieldSave}
                                                      onKeyDown={handleKeyDown}
                                                      autoFocus
                                                      className="inline-edit-input"
                                                      onClick={(e) => e.stopPropagation()}
                                                    />
                                                  ) : (
                                                    lot.vendor_lot_number || '-'
                                                  )}
                                                </td>
                                                <td>
                                                  {(() => {
                                                    // For raw materials, vendor lot number is the lot number
                                                    // For finished goods, show internal lot number
                                                    const item = lot.item
                                                    if (item && item.item_type === 'raw_material' && lot.vendor_lot_number) {
                                                      return lot.vendor_lot_number
                                                    }
                                                    return lot.lot_number || '-'
                                                  })()}
                                                </td>
                                                <td>{lot.po_number || '-'}</td>
                                                <td>
                                                  {lot.po_tracking_number ? (
                                                    <span>
                                                      {lot.po_tracking_number}
                                                      {lot.po_carrier && ` (${lot.po_carrier})`}
                                                    </span>
                                                  ) : '-'}
                                                </td>
                                                <td>{packSizeDisplay}</td>
                                                <td>{receivedDate}</td>
                                                <td
                                                  className="editable-cell"
                                                  onClick={() => handleFieldClick(lot.id, 'manufacture_date', mfgDate)}
                                                  title="Click to edit manufacturer production or pack date"
                                                >
                                                  {isEditingMfgDate ? (
                                                    <input
                                                      type="date"
                                                      value={editValue}
                                                      onChange={(e) => setEditValue(e.target.value)}
                                                      onBlur={handleFieldSave}
                                                      onKeyDown={handleKeyDown}
                                                      autoFocus
                                                      className="inline-edit-input"
                                                      onClick={(e) => e.stopPropagation()}
                                                    />
                                                  ) : (
                                                    mfgDate
                                                  )}
                                                </td>
                                                <td 
                                                  className="editable-cell"
                                                  onClick={() => handleFieldClick(lot.id, 'expiration_date', expDate)}
                                                  title="Click to edit expiration date"
                                                >
                                                  {isEditingExpDate ? (
                                                    <input
                                                      type="date"
                                                      value={editValue}
                                                      onChange={(e) => setEditValue(e.target.value)}
                                                      onBlur={handleFieldSave}
                                                      onKeyDown={handleKeyDown}
                                                      autoFocus
                                                      className="inline-edit-input"
                                                      onClick={(e) => e.stopPropagation()}
                                                    />
                                                  ) : (
                                                    expDate
                                                  )}
                                                </td>
                                                <td>{displayQty} {lotDisplayUnit}</td>
                                                <td
                                                  title={`Available (API quantity_available_for_use) = net after sales, hold, and in-progress production. Committed: ${prodCommit}, on hold: ${onHold}`}
                                                >
                                                  {displayRemaining} {lotDisplayUnit}
                                                </td>
                                                <td>
                                                  {(lotUnit !== 'ea' ? convertQuantity(qtyOnHold, lotUnit) : formatNumber(qtyOnHold, 0))} {lotDisplayUnit}
                                                </td>
                                                <td>
                                                  <span className={`status-badge status-${lot.status}`}>
                                                    {lot.status}
                                                  </span>
                                                </td>
                                                <td className="lot-table-col-committed">
                                                  {(() => {
                                                    const salesQty = lot.committed_to_sales_qty || 0
                                                    const prodQty = lot.committed_to_production_qty || 0
                                                    const lotUnit = lot.item.unit_of_measure
                                                    
                                                    if (salesQty > 0 && prodQty > 0) {
                                                      const displaySalesQty = lotUnit !== 'ea' ? convertQuantity(salesQty, lotUnit) : formatNumber(salesQty, 0)
                                                      const displayProdQty = lotUnit !== 'ea' ? convertQuantity(prodQty, lotUnit) : formatNumber(prodQty, 0)
                                                      return (
                                                        <div className="committed-info">
                                                          <span className="committed-badge committed-sales" title={`Committed to Sales: ${displaySalesQty} ${getDisplayUnit(lotUnit)}`}>
                                                            Sales: {displaySalesQty} {getDisplayUnit(lotUnit)}
                                                          </span>
                                                          <span className="committed-badge committed-production" title={`Committed to Production: ${displayProdQty} ${getDisplayUnit(lotUnit)}`}>
                                                            Prod: {displayProdQty} {getDisplayUnit(lotUnit)}
                                                          </span>
                                                        </div>
                                                      )
                                                    } else if (salesQty > 0) {
                                                      const displayQty = lotUnit !== 'ea' ? convertQuantity(salesQty, lotUnit) : formatNumber(salesQty, 0)
                                                      return (
                                                        <span className="committed-badge committed-sales" title={`Committed to Sales: ${displayQty} ${getDisplayUnit(lotUnit)}`}>
                                                          Sales: {displayQty} {getDisplayUnit(lotUnit)}
                                                        </span>
                                                      )
                                                    } else if (prodQty > 0) {
                                                      const displayQty = lotUnit !== 'ea' ? convertQuantity(prodQty, lotUnit) : formatNumber(prodQty, 0)
                                                      return (
                                                        <span className="committed-badge committed-production" title={`Committed to Production: ${displayQty} ${getDisplayUnit(lotUnit)}`}>
                                                          Prod: {displayQty} {getDisplayUnit(lotUnit)}
                                                        </span>
                                                      )
                                                    } else {
                                                      return <span className="committed-badge not-committed">-</span>
                                                    }
                                                  })()}
                                                </td>
                                                <td className="lot-table-col-actions">
                                                  {lot.coa_pdf_url && (
                                                    <>
                                                      <a
                                                        href={lot.coa_pdf_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="lot-action-btn view-coa"
                                                        title="Open master Certificate of Analysis (lot-level; customer COAs are on sales allocations)"
                                                      >
                                                        Master COA
                                                      </a>
                                                      <button
                                                        type="button"
                                                        className="lot-action-btn"
                                                        title="Rebuild stored COA PDFs from current lot data (e.g. after template or expiration updates)"
                                                        onClick={async () => {
                                                          try {
                                                            await regenerateLotCoa(lot.id)
                                                            alert('COA PDFs regenerated.')
                                                            loadData()
                                                          } catch (err: any) {
                                                            console.error(err)
                                                            alert(
                                                              err?.response?.data?.error ||
                                                                err?.message ||
                                                                'Could not regenerate COA.'
                                                            )
                                                          }
                                                        }}
                                                      >
                                                        Regenerate COA
                                                      </button>
                                                    </>
                                                  )}
                                                  {qtyOnHold > 0 && (
                                                    <button
                                                      type="button"
                                                      className="lot-action-btn release-hold"
                                                      onClick={() => void handleReleaseFromHold()}
                                                      title="Release from hold (e.g. after micro results)"
                                                    >
                                                      Release from hold
                                                    </button>
                                                  )}
                                                  <button
                                                    type="button"
                                                    className="lot-action-btn put-hold"
                                                    onClick={handlePutOnHold}
                                                    title="Put amount on hold (partial or full)"
                                                  >
                                                    Put on hold
                                                  </button>
                                                  <button
                                                    type="button"
                                                    className="lot-action-btn reconcile-btn"
                                                    onClick={handleReconcile}
                                                    title="Admin override: reconcile quantity to match reality (staff only)"
                                                  >
                                                    Reconcile
                                                  </button>
                                                </td>
                                              </tr>
                                            )
                                          })}
                                        </tbody>
                                      </table>
                                      </div>
                                      <div className="lot-deeper-wrap">
                                        <button
                                          type="button"
                                          className="lot-deeper-toggle"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            void handleDeeperToggle(vendorRowKey, vendorDetail)
                                          }}
                                        >
                                          {deeperSectionOpen.has(vendorRowKey)
                                            ? 'Hide depleted lots'
                                            : 'Deeper…'}
                                        </button>
                                        {deeperSectionOpen.has(vendorRowKey) &&
                                          (loadingDeeperLots.has(vendorRowKey) ? (
                                            <div className="loading-lots">Loading depleted lots...</div>
                                          ) : (
                                            <div className="lot-table-scroll lot-table-scroll--deeper">
                                              <DepletedLotTable
                                                lots={deeperLotDetails.get(vendorRowKey) || []}
                                                convertQuantity={convertQuantity}
                                                getDisplayUnit={getDisplayUnit}
                                                formatNumberFlexible={formatNumberFlexible}
                                              />
                                            </div>
                                          ))}
                                      </div>
                                    </div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        )
                      })}
      </React.Fragment>
    )
  }

  if (loading) {
    return (
      <div className="inventory-table-container">
        <div className="loading">Loading inventory...</div>
      </div>
    )
  }

  return (
    <div className="inventory-table-container">
      <div className="table-controls">
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
        <div className="inventory-table-tabs">
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'finished_good' ? 'active' : ''}`}
            onClick={() => setInventoryTable('finished_good')}
          >
            Finished Goods
          </button>
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'raw_material' ? 'active' : ''}`}
            onClick={() => setInventoryTable('raw_material')}
          >
            Raw Materials
          </button>
          <button
            type="button"
            className={`tab-btn ${inventoryTable === 'indirect_material' ? 'active' : ''}`}
            onClick={() => setInventoryTable('indirect_material')}
          >
            Indirect Materials (Packaging)
          </button>
        </div>
      </div>

      <div className="table-wrapper">
        <table
          className={`inventory-table${showOnOrderColumn ? '' : ' inventory-table--fg-no-on-order'}`}
        >
          <thead>
            <tr>
              <th>SKU</th>
              <th 
                className="sortable-header"
                onClick={() => handleSort('description')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                Description {sortConfig.key === 'description' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>Type</th>
              <th>Category</th>
              <th 
                className="sortable-header"
                onClick={() => handleSort('vendor')}
                style={{ cursor: 'pointer', userSelect: 'none' }}
              >
                Vendor {sortConfig.key === 'vendor' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>Pack Size</th>
              <th>Available</th>
              {showOnOrderColumn && <th>On Order</th>}
              <th>Alloc. Sales</th>
              <th>Alloc. Prod</th>
              <th>On Hold</th>
              <th>Lots</th>
            </tr>
          </thead>
          <tbody>
            {sortedInventoryDetails.length === 0 ? (
              <tr>
                <td colSpan={inventoryMainColSpan} className="no-data">No inventory found</td>
              </tr>
            ) : (
              inventorySections.map((section) => {
                if (section.type === 'family') {
                  const agg = aggregateFamilyInventoryRow(section.parentCode, section.members)
                  const unit = agg.pack_size_unit
                  const displayAllocSales = formatInventoryMeasure(agg, agg.allocated_to_sales, unit)
                  const displayAllocProd = formatInventoryMeasure(agg, agg.allocated_to_production, unit)
                  const displayOnHold = formatInventoryMeasure(agg, agg.on_hold, unit)
                  const displayOnOrder = showOnOrderColumn
                    ? formatInventoryMeasure(agg, agg.on_order, unit)
                    : ''
                  const displayAvailable = formatInventoryMeasure(agg, agg.available, unit)
                  const displayUnit = inventoryMeasureUnit(agg, unit)
                  const famOpen = expandedFamilies.has(section.parentCode)
                  return (
                    <React.Fragment key={`fam-${section.parentCode}`}>
                      <tr className="inventory-family-parent-row sku-master-row">
                        <td>
                          <div className="sku-cell">
                            <button
                              type="button"
                              className="expand-btn inventory-family-expand"
                              onClick={() => toggleFamilyExpansion(section.parentCode)}
                              title={famOpen ? 'Collapse pack SKUs' : 'Expand pack SKUs'}
                              aria-expanded={famOpen}
                            >
                              {famOpen ? '▼' : '▶'}
                            </button>
                            <strong className="sku-master-label">{section.parentCode}</strong>
                          </div>
                        </td>
                        <td>{agg.description}</td>
                        <td>
                          <span className={`inventory-type-badge inventory-type-badge--${agg.item_type || 'unknown'}`}>
                            {formatItemType(agg.item_type)}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`inventory-category-badge inventory-category-badge--${agg.product_category || 'none'}`}
                          >
                            {formatProductCategory(agg.product_category)}
                          </span>
                        </td>
                        <td>—</td>
                        <td>—</td>
                        <td className={agg.available > 0 ? 'available' : 'unavailable'}>
                          {displayAvailable} {displayUnit}
                        </td>
                        {showOnOrderColumn && (
                          <td className={agg.on_order > 0 ? 'on-order' : ''}>
                            {displayOnOrder} {displayUnit}
                          </td>
                        )}
                        <td>{displayAllocSales} {displayUnit}</td>
                        <td>{displayAllocProd} {displayUnit}</td>
                        <td>{displayOnHold} {displayUnit}</td>
                        <td>{agg.lot_count || 0}</td>
                      </tr>
                      {famOpen &&
                        section.members.map((m) => (
                          <React.Fragment key={m.item_sku}>
                            {renderSkuMasterSection(m, { underFamily: true })}
                          </React.Fragment>
                        ))}
                    </React.Fragment>
                  )
                }
                return (
                  <React.Fragment key={section.detail.item_sku}>
                    {renderSkuMasterSection(section.detail)}
                  </React.Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {inventoryDetails.length === 0 && !loading && (
        <div className="empty-state">
          No inventory found. Check in some items to get started.
        </div>
      )}

      {releaseCoaModal && (
        <ReleaseFromHoldCoaModal
          lotId={releaseCoaModal.lotId}
          lotLabel={releaseCoaModal.lotLabel}
          releaseQty={releaseCoaModal.releaseQty}
          preview={releaseCoaModal.preview}
          onClose={() => setReleaseCoaModal(null)}
          onSuccess={(updated) => {
            const snap = releaseCoaModal
            setReleaseCoaModal(null)
            if (!snap) return
            setLotDetails((prev) => {
              const lots = prev.get(snap.vendorRowKey)
              if (!lots || !updated) return prev
              const updatedLots = lots.map((l) =>
                l.id === snap.lotId ? { ...l, ...updated } : l
              )
              return new Map([...prev, [snap.vendorRowKey, updatedLots]])
            })
            void loadData()
          }}
        />
      )}
    </div>
  )
}

export default InventoryTable
