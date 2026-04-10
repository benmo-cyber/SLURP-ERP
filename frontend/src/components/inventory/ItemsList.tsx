import { useState, useEffect, Fragment } from 'react'
import { getItems, updateItem, deleteItem, getItemPackSizes, createItemPackSize, updateItemPackSize, deleteItemPackSize, getLotsByItemId } from '../../api/inventory'
import { getFormulas } from '../../api/inventory'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import { formatCurrency } from '../../utils/formatNumber'
import ConfirmDialog from '../common/ConfirmDialog'
import { SkuFamilyWarningIcon, type SkuFamilyWarning } from './SkuFamilyWarningIcon'
import './InventoryTable.css'
import './ItemsList.css'

interface ItemPackSize {
  id: number
  item: number
  pack_size: number
  pack_size_unit: string
  price?: number
  description?: string
  is_default: boolean
  is_active: boolean
  pack_size_display?: string
}

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  vendor_item_name?: string
  vendor_item_number?: string | null
  item_type: string
  unit_of_measure: string
  vendor?: string
  pack_size?: number
  price?: number
  on_order: number
  approved_for_formulas: boolean
  product_category?: string | null
  pack_sizes?: ItemPackSize[]
  default_pack_size?: ItemPackSize
  sku_family_warnings?: SkuFamilyWarning[]
  sku_parent_code?: string | null
  sku_pack_suffix?: string | null
}

type ItemLotRow = {
  id: number
  lot_number?: string | null
  vendor_lot_number?: string | null
  quantity_remaining?: number | null
  quantity?: number | null
  received_date?: string | null
  expiration_date?: string | null
  status?: string | null
  po_number?: string | null
}

function inventoryTableForItem(item: Item): 'finished_good' | 'raw_material' | 'indirect_material' {
  const t = item.item_type
  if (t === 'finished_good' || t === 'distributed_item') return 'finished_good'
  if (t === 'raw_material') return 'raw_material'
  if (t === 'indirect_material') return 'indirect_material'
  return 'raw_material'
}

function sortFamilyMembers(items: Item[]): Item[] {
  const pc = (i: Item) => (i.sku_parent_code || '').trim().toUpperCase()
  const suf = (i: Item) => (i.sku_pack_suffix || '').trim()
  return [...items].sort((a, b) => {
    const aMaster = !suf(a) || (a.sku || '').trim().toUpperCase() === pc(a)
    const bMaster = !suf(b) || (b.sku || '').trim().toUpperCase() === pc(b)
    if (aMaster !== bMaster) return aMaster ? -1 : 1
    return (a.sku || '').localeCompare(b.sku || '')
  })
}

function shouldShowFamilyParentRow(members: Item[]): boolean {
  if (members.length > 1) return true
  if (members.length === 1) {
    const m = members[0]
    return !!(m.sku_pack_suffix && (m.sku_parent_code || '').trim())
  }
  return false
}

type ItemsSection =
  | { kind: 'family'; parentCode: string; members: Item[] }
  | { kind: 'sku_group'; sku: string; members: Item[] }

function buildItemSections(filteredItems: Item[]): ItemsSection[] {
  const withParent: Record<string, Item[]> = {}
  const withoutParent: Item[] = []
  for (const item of filteredItems) {
    const p = (item.sku_parent_code || '').trim()
    if (p) {
      if (!withParent[p]) withParent[p] = []
      withParent[p].push(item)
    } else {
      withoutParent.push(item)
    }
  }
  const sections: ItemsSection[] = []
  for (const parentCode of Object.keys(withParent).sort()) {
    sections.push({
      kind: 'family',
      parentCode,
      members: sortFamilyMembers(withParent[parentCode]),
    })
  }
  const groupedBySku = withoutParent.reduce((acc, item) => {
    if (!acc[item.sku]) acc[item.sku] = []
    acc[item.sku].push(item)
    return acc
  }, {} as Record<string, Item[]>)
  for (const sku of Object.keys(groupedBySku).sort()) {
    groupedBySku[sku].sort((a, b) => (a.vendor || '').localeCompare(b.vendor || ''))
    sections.push({ kind: 'sku_group', sku, members: groupedBySku[sku] })
  }
  return sections
}

function formatItemType(type: string): string {
  return (type || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatProductCategory(cat: string | null | undefined): string {
  if (!cat) return '—'
  const map: Record<string, string> = {
    natural_colors: 'Natural Colors',
    synthetic_colors: 'Synthetic Colors',
    antioxidants: 'Antioxidants',
    other: 'Other',
  }
  return map[cat] || cat.replace(/_/g, ' ')
}

function ItemsList() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<Partial<Item>>({})
  const [filter, setFilter] = useState<string>('all')
  const [showUnfkConfirm, setShowUnfkConfirm] = useState(false)
  const [itemToUnfk, setItemToUnfk] = useState<Item | null>(null)
  const [formulas, setFormulas] = useState<any[]>([])
  const [fpsLinks, setFpsLinks] = useState<Map<number, number>>(new Map())
  const [showPackSizeModal, setShowPackSizeModal] = useState(false)
  const [selectedItemForPackSize, setSelectedItemForPackSize] = useState<Item | null>(null)
  const [packSizes, setPackSizes] = useState<ItemPackSize[]>([])
  const [editingPackSizeId, setEditingPackSizeId] = useState<number | null>(null)
  const [packSizeForm, setPackSizeForm] = useState({
    pack_size: '',
    pack_size_unit: 'lbs',
    price: '',
    description: '',
    is_default: false,
    is_active: true
  })

  /** Material family (sku_parent_code) rows — click to show pack variants / vendor rows. */
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set())
  /** Per item row: load on-hand lots (same rules as Inventory). */
  const [expandedLotsItemId, setExpandedLotsItemId] = useState<Set<number>>(new Set())
  const [itemLotsById, setItemLotsById] = useState<Map<number, ItemLotRow[]>>(new Map())
  const [loadingItemLots, setLoadingItemLots] = useState<Set<number>>(new Set())

  useEffect(() => {
    loadItems()
    loadFormulas()
  }, [filter])

  useEffect(() => {
    // Load FPS links for finished goods
    loadFpsLinks()
  }, [items])

  const loadFormulas = async () => {
    try {
      const data = await getFormulas()
      setFormulas(data)
    } catch (error) {
      console.error('Failed to load formulas:', error)
    }
  }

  const loadFpsLinks = async () => {
    if (items.length === 0) {
      setFpsLinks(new Map())
      return
    }
    
    // Get unique item IDs for finished goods
    const finishedGoodItemIds = Array.from(new Set(
      items
        .filter(item => item.item_type === 'finished_good')
        .map(item => item.id)
    ))

    if (finishedGoodItemIds.length === 0) {
      setFpsLinks(new Map())
      return
    }

    // Load FPS for each finished good in parallel
    const links = new Map<number, number>()
    const promises = finishedGoodItemIds.map(async (itemId) => {
      try {
        const fps = await getFinishedProductSpecification(itemId)
        if (fps && fps.id) {
          links.set(itemId, fps.id)
        }
      } catch (error) {
        // FPS doesn't exist for this item, that's okay
      }
    })
    
    await Promise.all(promises)
    setFpsLinks(new Map(links))
  }

  const loadItems = async () => {
    try {
      setLoading(true)
      const data = await getItems()
      setItems(data)
    } catch (error) {
      console.error('Failed to load items:', error)
      alert('Failed to load items')
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = (item: Item) => {
    setEditingId(item.id)
    setEditForm({
      sku: item.sku,
      name: item.name,
      vendor_item_name: item.vendor_item_name,
      vendor_item_number: item.vendor_item_number,
      price: item.price,
      pack_size: item.pack_size,
      vendor: item.vendor,
      description: item.description,
      item_type: item.item_type,
      product_category: item.product_category,
      unit_of_measure: item.unit_of_measure,
    })
  }

  const handleCancel = () => {
    setEditingId(null)
    setEditForm({})
  }

  const handleSave = async (id: number) => {
    try {
      // Validate required fields
      if (!editForm.sku || editForm.sku.trim() === '') {
        alert('SKU is required')
        return
      }
      if (!editForm.name || editForm.name.trim() === '') {
        alert('Name is required')
        return
      }
      
      // Clean up the data - remove empty strings and convert to proper types
      const updateData: any = {}
      if (editForm.sku !== undefined) updateData.sku = editForm.sku.trim()
      if (editForm.name !== undefined) updateData.name = editForm.name.trim()
      if (editForm.vendor !== undefined) updateData.vendor = editForm.vendor?.trim() || null
      if (editForm.description !== undefined) updateData.description = editForm.description?.trim() || null
      if (editForm.vendor_item_name !== undefined) updateData.vendor_item_name = editForm.vendor_item_name?.trim() || null
      if (editForm.vendor_item_number !== undefined) updateData.vendor_item_number = editForm.vendor_item_number?.trim() || null
      if (editForm.price !== undefined) updateData.price = editForm.price || null
      if (editForm.pack_size !== undefined) updateData.pack_size = editForm.pack_size || null
      // Include required fields to avoid validation errors
      if (editForm.item_type !== undefined) updateData.item_type = editForm.item_type
      if (editForm.product_category !== undefined) updateData.product_category = editForm.product_category || null
      if (editForm.unit_of_measure !== undefined) updateData.unit_of_measure = editForm.unit_of_measure
      console.log('Saving item with data:', updateData)
      await updateItem(id, updateData)
      alert('Item updated successfully. CostMaster has been synced.')
      setEditingId(null)
      setEditForm({})
      loadItems()
    } catch (error: any) {
      console.error('Failed to update item:', error)
      console.error('Error response:', error.response)
      console.error('Error data:', error.response?.data)
      
      // Try to get detailed error message
      let errorMessage = 'Failed to update item'
      if (error.response?.data) {
        if (error.response.data.detail) {
          errorMessage = error.response.data.detail
        } else if (error.response.data.error) {
          errorMessage = error.response.data.error
        } else if (typeof error.response.data === 'string') {
          errorMessage = error.response.data
        } else if (error.response.data.non_field_errors) {
          errorMessage = error.response.data.non_field_errors.join(', ')
        } else {
          // Try to format validation errors
          const errorParts: string[] = []
          for (const [field, messages] of Object.entries(error.response.data)) {
            if (Array.isArray(messages)) {
              errorParts.push(`${field}: ${messages.join(', ')}`)
            } else if (typeof messages === 'string') {
              errorParts.push(`${field}: ${messages}`)
            } else {
              errorParts.push(`${field}: ${JSON.stringify(messages)}`)
            }
          }
          if (errorParts.length > 0) {
            errorMessage = errorParts.join('\n')
          } else {
            errorMessage = JSON.stringify(error.response.data)
          }
        }
      }
      alert(errorMessage)
    }
  }

  const handleChange = (field: keyof Item, value: any) => {
    setEditForm({ ...editForm, [field]: value })
  }

  const handleUnfk = (item: Item) => {
    setItemToUnfk(item)
    setShowUnfkConfirm(true)
  }

  const confirmUnfk = async () => {
    if (!itemToUnfk) return

    // Check if item is a finished good with a formula
    const hasFormula = itemToUnfk.item_type === 'finished_good' && 
      formulas.some(f => f.finished_good?.id === itemToUnfk.id)

    const itemType = itemToUnfk.item_type === 'finished_good' ? 'finished good' : 'item'
    const formulaWarning = hasFormula ? ' This will also delete the associated formula and FPS.' : ''

    if (
      !confirm(
        `Permanently delete this ${itemType} from the catalog? This does not reverse batches or receipts.${formulaWarning}\n\nThis cannot be undone.`,
      )
    ) {
      setShowUnfkConfirm(false)
      setItemToUnfk(null)
      return
    }

    try {
      await deleteItem(itemToUnfk.id)
      alert(`${itemType.charAt(0).toUpperCase() + itemType.slice(1)} deleted successfully`)
      setShowUnfkConfirm(false)
      setItemToUnfk(null)
      loadItems()
      loadFormulas()
    } catch (error: any) {
      console.error('Failed to delete item:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to delete item')
    }
  }

  const handleManagePackSizes = async (item: Item) => {
    setSelectedItemForPackSize(item)
    setShowPackSizeModal(true)
    setEditingPackSizeId(null)
    setPackSizeForm({
      pack_size: '',
      pack_size_unit: 'lbs',
      price: '',
      description: '',
      is_default: false,
      is_active: true
    })
    
    try {
      const data = await getItemPackSizes(item.id)
      setPackSizes(data)
    } catch (error) {
      console.error('Failed to load pack sizes:', error)
      alert('Failed to load pack sizes')
      setPackSizes([])
    }
  }

  const handlePackSizeSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedItemForPackSize) return

    try {
      const payload: any = {
        item: selectedItemForPackSize.id,
        pack_size: parseFloat(packSizeForm.pack_size),
        pack_size_unit: packSizeForm.pack_size_unit,
        is_default: packSizeForm.is_default,
        is_active: packSizeForm.is_active
      }
      
      if (packSizeForm.price) {
        payload.price = parseFloat(packSizeForm.price)
      }
      if (packSizeForm.description) {
        payload.description = packSizeForm.description.trim()
      }

      if (editingPackSizeId) {
        await updateItemPackSize(editingPackSizeId, payload)
        alert('Pack size updated successfully')
      } else {
        await createItemPackSize(payload)
        alert('Pack size created successfully')
      }

      // Reload pack sizes
      const data = await getItemPackSizes(selectedItemForPackSize.id)
      setPackSizes(data)
      
      // Reset form
      setPackSizeForm({
        pack_size: '',
        pack_size_unit: 'lbs',
        price: '',
        description: '',
        is_default: false,
        is_active: true
      })
      setEditingPackSizeId(null)
    } catch (error: any) {
      console.error('Failed to save pack size:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to save pack size')
    }
  }

  const handleEditPackSize = (packSize: ItemPackSize) => {
    setEditingPackSizeId(packSize.id)
    setPackSizeForm({
      pack_size: packSize.pack_size.toString(),
      pack_size_unit: packSize.pack_size_unit,
      price: packSize.price?.toString() || '',
      description: packSize.description || '',
      is_default: packSize.is_default,
      is_active: packSize.is_active
    })
  }

  const handleDeletePackSize = async (id: number) => {
    if (!confirm('Are you sure you want to delete this pack size?')) return

    try {
      await deleteItemPackSize(id)
      alert('Pack size deleted successfully')
      
      if (selectedItemForPackSize) {
        const data = await getItemPackSizes(selectedItemForPackSize.id)
        setPackSizes(data)
      }
    } catch (error: any) {
      console.error('Failed to delete pack size:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to delete pack size')
    }
  }

  const toggleFamilyExpanded = (parentCode: string) => {
    setExpandedFamilies((prev) => {
      const next = new Set(prev)
      if (next.has(parentCode)) next.delete(parentCode)
      else next.add(parentCode)
      return next
    })
  }

  const toggleItemLots = async (item: Item) => {
    const id = item.id
    if (expandedLotsItemId.has(id)) {
      setExpandedLotsItemId((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      return
    }
    setExpandedLotsItemId((prev) => new Set(prev).add(id))
    if (itemLotsById.has(id)) return
    setLoadingItemLots((s) => new Set(s).add(id))
    try {
      const tab = inventoryTableForItem(item)
      const rows = await getLotsByItemId(id, tab)
      setItemLotsById((m) => new Map(m).set(id, Array.isArray(rows) ? rows : []))
    } catch (e) {
      console.error(e)
      setItemLotsById((m) => new Map(m).set(id, []))
    } finally {
      setLoadingItemLots((s) => {
        const n = new Set(s)
        n.delete(id)
        return n
      })
    }
  }

  const filteredItems = items.filter(item => {
    if (filter === 'all') return true
    if (filter === 'raw_material') return item.item_type === 'raw_material'
    if (filter === 'distributed_item') return item.item_type === 'distributed_item'
    if (filter === 'finished_good') return item.item_type === 'finished_good'
    if (filter === 'indirect_material') return item.item_type === 'indirect_material'
    return true
  })

  const itemSections = buildItemSections(filteredItems)

  const formatLotDate = (v: string | null | undefined) => {
    if (!v) return '—'
    try {
      const d = new Date(v)
      if (Number.isNaN(d.getTime())) return v
      return d.toLocaleDateString()
    } catch {
      return v
    }
  }

  const renderItemRows = (item: Item, skuCell: 'primary' | 'sub' | 'child', rowClassName: string) => {
    const lotsOpen = expandedLotsItemId.has(item.id)
    const lots = itemLotsById.get(item.id)
    const lotsLoading = loadingItemLots.has(item.id)
    const skuPrimary = skuCell === 'primary'
    return (
      <Fragment key={`item-${item.id}`}>
        <tr className={rowClassName}>
          <td>
            {editingId === item.id ? (
              <input
                type="text"
                value={editForm.sku || ''}
                onChange={(e) => handleChange('sku', e.target.value)}
                className="edit-input"
              />
            ) : skuPrimary ? (
              <>
                {item.item_type === 'finished_good' && fpsLinks.has(item.id) ? (
                  <a
                    href={getFpsPdfUrl(fpsLinks.get(item.id)!)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="fps-link"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <strong>{item.sku}</strong>
                  </a>
                ) : (
                  <strong>{item.sku}</strong>
                )}
                <SkuFamilyWarningIcon warnings={item.sku_family_warnings} />
              </>
            ) : skuCell === 'sub' ? (
              <span className="sku-cell-subrow">
                <span className="items-list-sku-tree">↳</span>
                <SkuFamilyWarningIcon warnings={item.sku_family_warnings} />
              </span>
            ) : (
              <span className="sku-cell-subrow">
                <span className="items-list-sku-tree">↳</span>
                <span className="items-list-child-sku">{item.sku}</span>
                <SkuFamilyWarningIcon warnings={item.sku_family_warnings} />
              </span>
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <input
                type="text"
                value={editForm.name || ''}
                onChange={(e) => handleChange('name', e.target.value)}
                className="edit-input"
              />
            ) : skuPrimary ? (
              item.name
            ) : (
              <span className="items-list-secondary-text">{item.name}</span>
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <input
                type="text"
                value={editForm.vendor_item_name ?? ''}
                onChange={(e) => handleChange('vendor_item_name', e.target.value)}
                className="edit-input"
                placeholder="Vendor description"
              />
            ) : (
              (item as Item).vendor_item_name || '-'
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <input
                type="text"
                value={editForm.vendor_item_number ?? ''}
                onChange={(e) => handleChange('vendor_item_number', e.target.value)}
                className="edit-input"
                placeholder="Vendor catalog #"
              />
            ) : (
              item.vendor_item_number || '-'
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <input
                type="text"
                value={editForm.vendor || ''}
                onChange={(e) => handleChange('vendor', e.target.value)}
                className="edit-input"
              />
            ) : (
              <strong>{item.vendor || '-'}</strong>
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <input
                type="number"
                step="0.01"
                value={editForm.pack_size || ''}
                onChange={(e) => handleChange('pack_size', parseFloat(e.target.value) || undefined)}
                className="edit-input"
              />
            ) : (
              <>
                {item.pack_size != null ? item.pack_size : '-'}
                {item.sku_pack_suffix ? (
                  <span className="items-list-pack-suffix" title="Pack code from SKU family">
                    {' '}
                    ({item.sku_pack_suffix})
                  </span>
                ) : null}
              </>
            )}
          </td>
          <td>{item.unit_of_measure}</td>
          <td>
            {editingId === item.id ? (
              <input
                type="number"
                step="0.01"
                value={editForm.price || ''}
                onChange={(e) => handleChange('price', parseFloat(e.target.value) || undefined)}
                className="edit-input"
              />
            ) : (
              item.price ? formatCurrency(item.price) : '-'
            )}
          </td>
          <td>
            <span className={`inventory-type-badge inventory-type-badge--${item.item_type || 'unknown'}`}>
              {formatItemType(item.item_type)}
            </span>
          </td>
          <td>
            {editingId === item.id ? (
              <select
                value={editForm.product_category ?? ''}
                onChange={(e) => handleChange('product_category', e.target.value || null)}
                className="edit-input"
              >
                <option value="">—</option>
                <option value="natural_colors">Natural Colors</option>
                <option value="synthetic_colors">Synthetic Colors</option>
                <option value="antioxidants">Antioxidants</option>
                <option value="other">Other</option>
              </select>
            ) : (
              <span className={`inventory-category-badge inventory-category-badge--${item.product_category || 'none'}`}>
                {formatProductCategory(item.product_category)}
              </span>
            )}
          </td>
          <td>
            {editingId === item.id ? (
              <div className="action-buttons">
                <button onClick={() => handleSave(item.id)} className="btn btn-sm btn-primary">
                  Save
                </button>
                <button onClick={handleCancel} className="btn btn-sm btn-secondary">
                  Cancel
                </button>
              </div>
            ) : (
              <div className="action-buttons">
                <button onClick={() => handleEdit(item)} className="btn btn-sm btn-primary">
                  Edit
                </button>
                <button
                  onClick={() => handleManagePackSizes(item)}
                  className="btn btn-sm btn-secondary"
                  title="Manage Pack Sizes"
                >
                  Pack Sizes
                </button>
                <button
                  type="button"
                  onClick={() => void toggleItemLots(item)}
                  className="btn btn-sm btn-secondary"
                  title="Load on-hand lots for this item"
                >
                  {lotsOpen ? 'Hide lots' : 'Lots'}
                </button>
                <button
                  onClick={() => handleUnfk(item)}
                  className="btn btn-sm btn-danger"
                  title="Delete this item record (not a batch or receipt reversal)"
                >
                  Delete item
                </button>
              </div>
            )}
          </td>
        </tr>
        {lotsOpen ? (
          <tr className="items-list-lots-row">
            <td colSpan={11}>
              {lotsLoading ? (
                <div className="items-list-lots-loading">Loading lots…</div>
              ) : !lots || lots.length === 0 ? (
                <div className="items-list-lots-empty">
                  No on-hand lots for this item (or none match inventory rules for this item type).
                </div>
              ) : (
                <div className="items-list-lots-inner">
                  <table className="items-list-lots-table">
                    <thead>
                      <tr>
                        <th>Lot #</th>
                        <th>Vendor lot</th>
                        <th>On hand</th>
                        <th>Received</th>
                        <th>Expires</th>
                        <th>PO</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lots.map((lot: ItemLotRow) => (
                        <tr key={lot.id}>
                          <td>{lot.lot_number || '—'}</td>
                          <td>{lot.vendor_lot_number || '—'}</td>
                          <td>{lot.quantity_remaining != null ? lot.quantity_remaining : '—'}</td>
                          <td>{formatLotDate(lot.received_date)}</td>
                          <td>{formatLotDate(lot.expiration_date)}</td>
                          <td>{lot.po_number || '—'}</td>
                          <td>{lot.status || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </td>
          </tr>
        ) : null}
      </Fragment>
    )
  }

  if (loading) {
    return (
      <div className="inventory-table-container items-management">
        <div className="loading">Loading items...</div>
      </div>
    )
  }

  return (
    <div className="inventory-table-container items-management">
      <div className="table-controls items-management-toolbar">
        <h2 className="items-management-title">Items Management</h2>
        <div className="items-filters items-management-filter-chips" role="group" aria-label="Filter by item type">
          <button
            type="button"
            className={`toggle-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All
          </button>
          <button
            type="button"
            className={`toggle-btn ${filter === 'raw_material' ? 'active' : ''}`}
            onClick={() => setFilter('raw_material')}
          >
            Raw Materials
          </button>
          <button
            type="button"
            className={`toggle-btn ${filter === 'distributed_item' ? 'active' : ''}`}
            onClick={() => setFilter('distributed_item')}
          >
            Distributed
          </button>
          <button
            type="button"
            className={`toggle-btn ${filter === 'finished_good' ? 'active' : ''}`}
            onClick={() => setFilter('finished_good')}
          >
            Finished Goods
          </button>
          <button
            type="button"
            className={`toggle-btn ${filter === 'indirect_material' ? 'active' : ''}`}
            onClick={() => setFilter('indirect_material')}
          >
            Indirect Materials
          </button>
        </div>
      </div>

      <div className="table-wrapper items-management-table-wrap">
        <table className="inventory-table items-management-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Name</th>
              <th>Vendor Item Name</th>
              <th>Vendor #</th>
              <th>Vendor</th>
              <th>Pack Size</th>
              <th>Unit</th>
              <th>Price</th>
              <th>Type</th>
              <th>Category</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 ? (
              <tr className="items-management-empty-row">
                <td colSpan={11}>No items match this filter.</td>
              </tr>
            ) : (
              itemSections.flatMap((section) => {
                if (section.kind === 'family') {
                  const { parentCode, members } = section
                  const showParent = shouldShowFamilyParentRow(members)
                  if (!showParent) {
                    return members.map((item, idx) =>
                      renderItemRows(
                        item,
                        idx === 0 ? 'primary' : 'sub',
                        idx === 0 && members.length > 1 ? 'sku-group-first' : ''
                      )
                    )
                  }
                  const famOpen = expandedFamilies.has(parentCode)
                  const vendorCount = new Set(members.map((m) => (m.vendor || '').trim()).filter(Boolean)).size
                  const parentRow = (
                    <tr key={`fam-head-${parentCode}`} className="items-list-parent-row">
                      <td colSpan={11}>
                        <button
                          type="button"
                          className="items-list-parent-toggle"
                          onClick={() => toggleFamilyExpanded(parentCode)}
                          aria-expanded={famOpen}
                        >
                          <span className="items-list-chevron" aria-hidden>
                            {famOpen ? '▼' : '▶'}
                          </span>
                          <strong className="items-list-parent-code">{parentCode}</strong>
                          <span className="items-list-parent-meta">
                            {members.length} variant{members.length !== 1 ? 's' : ''}
                            {vendorCount > 0
                              ? ` · ${vendorCount} vendor${vendorCount !== 1 ? 's' : ''}`
                              : ''}
                            <span className="items-list-parent-hint"> — click to show pack sizes / SKUs / vendors</span>
                          </span>
                        </button>
                      </td>
                    </tr>
                  )
                  if (!famOpen) return [parentRow]
                  return [
                    parentRow,
                    ...members.map((item) => renderItemRows(item, 'child', 'items-list-child-row')),
                  ]
                }
                const { members } = section
                return members.map((item, index) =>
                  renderItemRows(
                    item,
                    index === 0 ? 'primary' : 'sub',
                    index === 0 && members.length > 1 ? 'sku-group-first' : ''
                  )
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {showUnfkConfirm && (
        <ConfirmDialog
          message="Permanently delete this item from the catalog? This does not reverse batches or receipts. This cannot be undone."
          onConfirm={confirmUnfk}
          onCancel={() => {
            setShowUnfkConfirm(false)
            setItemToUnfk(null)
          }}
        />
      )}

      {showPackSizeModal && selectedItemForPackSize && (
        <div className="modal-overlay" onClick={() => setShowPackSizeModal(false)}>
          <div className="modal-content pack-size-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px' }}>
            <div className="modal-header">
              <h3>Manage Pack Sizes</h3>
              <div className="modal-subtitle">{selectedItemForPackSize.sku} - {selectedItemForPackSize.name}</div>
              <button onClick={() => setShowPackSizeModal(false)} className="close-btn">×</button>
            </div>
            
            <div className="modal-body">
              <div className="pack-size-form-section">
                <h4>{editingPackSizeId ? 'Edit Pack Size' : 'Add New Pack Size'}</h4>
                <form onSubmit={handlePackSizeSubmit} className="pack-size-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="pack_size">Pack Size *</label>
                      <input
                        id="pack_size"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={packSizeForm.pack_size}
                        onChange={(e) => setPackSizeForm({ ...packSizeForm, pack_size: e.target.value })}
                        required
                        placeholder="e.g., 2000"
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="pack_size_unit">Unit *</label>
                      <select
                        id="pack_size_unit"
                        value={packSizeForm.pack_size_unit}
                        onChange={(e) => setPackSizeForm({ ...packSizeForm, pack_size_unit: e.target.value })}
                        required
                      >
                        <option value="lbs">Pounds (lbs)</option>
                        <option value="kg">Kilograms (kg)</option>
                        <option value="gal">Gallons (gal)</option>
                        <option value="ea">Each (ea)</option>
                        <option value="pcs">Pieces (pcs)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="pack_size_price">Price (Optional)</label>
                      <input
                        id="pack_size_price"
                        type="number"
                        step="0.01"
                        min="0"
                        value={packSizeForm.price}
                        onChange={(e) => setPackSizeForm({ ...packSizeForm, price: e.target.value })}
                        placeholder="Price per pack"
                      />
                    </div>
                  </div>
                  
                  <div className="form-group">
                    <label htmlFor="pack_size_description">Description (Optional)</label>
                    <input
                      id="pack_size_description"
                      type="text"
                      value={packSizeForm.description}
                      onChange={(e) => setPackSizeForm({ ...packSizeForm, description: e.target.value })}
                      placeholder="e.g., 2000lb IBC, 5 gallon pail"
                    />
                  </div>
                  
                  <div className="form-checkboxes">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={packSizeForm.is_default}
                        onChange={(e) => setPackSizeForm({ ...packSizeForm, is_default: e.target.checked })}
                      />
                      <span>Set as default pack size</span>
                    </label>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={packSizeForm.is_active}
                        onChange={(e) => setPackSizeForm({ ...packSizeForm, is_active: e.target.checked })}
                      />
                      <span>Active (available for use)</span>
                    </label>
                  </div>
                  
                  <div className="form-actions">
                    <button type="submit" className="btn btn-primary">
                      {editingPackSizeId ? 'Update Pack Size' : 'Add Pack Size'}
                    </button>
                    {editingPackSizeId && (
                      <button
                        type="button"
                        onClick={() => {
                          setPackSizeForm({
                            pack_size: '',
                            pack_size_unit: 'lbs',
                            price: '',
                            description: '',
                            is_default: false,
                            is_active: true
                          })
                          setEditingPackSizeId(null)
                        }}
                        className="btn btn-secondary"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </form>
              </div>

              <div className="pack-size-list-section">
                <h4>Existing Pack Sizes ({packSizes.length})</h4>
                {packSizes.length === 0 ? (
                  <div className="empty-state">
                    <p>No pack sizes have been defined yet.</p>
                    <p className="empty-state-hint">Add a pack size above to get started.</p>
                  </div>
                ) : (
                  <div className="pack-size-table-wrapper">
                    <table className="pack-size-table">
                      <thead>
                        <tr>
                          <th>Pack Size</th>
                          <th>Description</th>
                          <th>Price</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {packSizes.map((ps) => (
                          <tr key={ps.id} className={ps.is_default ? 'default-pack-size' : ''}>
                            <td>
                              <strong>{ps.pack_size} {ps.pack_size_unit}</strong>
                              {ps.is_default && <span className="badge badge-primary">Default</span>}
                            </td>
                            <td>{ps.description || <span className="text-muted">No description</span>}</td>
                            <td>{ps.price ? formatCurrency(ps.price) : <span className="text-muted">—</span>}</td>
                            <td>
                              {ps.is_active ? (
                                <span className="badge badge-success">Active</span>
                              ) : (
                                <span className="badge badge-secondary">Inactive</span>
                              )}
                            </td>
                            <td>
                              <div className="action-buttons">
                                <button
                                  onClick={() => handleEditPackSize(ps)}
                                  className="btn btn-sm btn-primary"
                                  title="Edit pack size"
                                >
                                  Edit
                                </button>
                                <button
                                  onClick={() => handleDeletePackSize(ps.id)}
                                  className="btn btn-sm btn-danger"
                                  title="Delete pack size"
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ItemsList
