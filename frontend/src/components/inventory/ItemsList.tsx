import { useState, useEffect } from 'react'
import { getItems, updateItem, deleteItem } from '../../api/inventory'
import { getFormulas } from '../../api/inventory'
import { getFinishedProductSpecification, getFpsPdfUrl } from '../../api/production'
import { formatCurrency } from '../../utils/formatNumber'
import ConfirmDialog from '../common/ConfirmDialog'
import './ItemsList.css'

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  item_type: string
  unit_of_measure: string
  vendor?: string
  pack_size?: number
  price?: number
  on_order: number
  approved_for_formulas: boolean
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
      price: item.price,
      pack_size: item.pack_size,
      vendor: item.vendor,
      description: item.description,
      item_type: item.item_type,
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
      if (editForm.price !== undefined) updateData.price = editForm.price || null
      if (editForm.pack_size !== undefined) updateData.pack_size = editForm.pack_size || null
      // Include required fields to avoid validation errors
      if (editForm.item_type !== undefined) updateData.item_type = editForm.item_type
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

    if (!confirm(`Are you sure you want to UNFK this ${itemType}? This action cannot be undone.${formulaWarning}`)) {
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

  const filteredItems = items.filter(item => {
    if (filter === 'all') return true
    if (filter === 'raw_material') return item.item_type === 'raw_material'
    if (filter === 'finished_good') return item.item_type === 'finished_good'
    if (filter === 'indirect_material') return item.item_type === 'indirect_material'
    return true
  })

  // Group items by SKU for better organization
  const groupedBySku = filteredItems.reduce((acc, item) => {
    if (!acc[item.sku]) {
      acc[item.sku] = []
    }
    acc[item.sku].push(item)
    return acc
  }, {} as Record<string, Item[]>)

  // Sort SKUs and items within each SKU group
  const sortedSkus = Object.keys(groupedBySku).sort()
  sortedSkus.forEach(sku => {
    groupedBySku[sku].sort((a, b) => (a.vendor || '').localeCompare(b.vendor || ''))
  })

  if (loading) {
    return <div className="loading">Loading items...</div>
  }

  return (
    <div className="items-list">
      <div className="items-header">
        <h2>Items Management</h2>
        <div className="items-filters">
          <button
            className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All
          </button>
          <button
            className={`filter-btn ${filter === 'raw_material' ? 'active' : ''}`}
            onClick={() => setFilter('raw_material')}
          >
            Raw Materials
          </button>
          <button
            className={`filter-btn ${filter === 'finished_good' ? 'active' : ''}`}
            onClick={() => setFilter('finished_good')}
          >
            Finished Goods
          </button>
          <button
            className={`filter-btn ${filter === 'indirect_material' ? 'active' : ''}`}
            onClick={() => setFilter('indirect_material')}
          >
            Indirect Materials
          </button>
        </div>
      </div>

      <div className="items-table-wrapper">
        <table className="items-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Name</th>
              <th>Vendor</th>
              <th>Pack Size</th>
              <th>Unit</th>
              <th>Price</th>
              <th>Type</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">No items found</td>
              </tr>
            ) : (
              sortedSkus.flatMap((sku) => {
                const skuItems = groupedBySku[sku]
                return skuItems.map((item, index) => (
                  <tr 
                    key={item.id}
                    className={index === 0 && skuItems.length > 1 ? 'sku-group-first' : ''}
                  >
                    <td>
                      {editingId === item.id ? (
                        <input
                          type="text"
                          value={editForm.sku || ''}
                          onChange={(e) => handleChange('sku', e.target.value)}
                          className="edit-input"
                        />
                      ) : (
                        index === 0 ? (
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
                          </>
                        ) : (
                          <span style={{ color: '#999', fontStyle: 'italic' }}>↳</span>
                        )
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
                      ) : (
                        index === 0 ? item.name : <span style={{ color: '#666' }}>{item.name}</span>
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
                        item.pack_size || '-'
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
                    <td>{item.item_type}</td>
                    <td>
                      {editingId === item.id ? (
                        <div className="action-buttons">
                          <button
                            onClick={() => handleSave(item.id)}
                            className="btn btn-sm btn-primary"
                          >
                            Save
                          </button>
                          <button
                            onClick={handleCancel}
                            className="btn btn-sm btn-secondary"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="action-buttons">
                          <button
                            onClick={() => handleEdit(item)}
                            className="btn btn-sm btn-primary"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleUnfk(item)}
                            className="btn btn-sm btn-danger"
                          >
                            UNFK
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              })
            )}
          </tbody>
        </table>
      </div>

      {showUnfkConfirm && (
        <ConfirmDialog
          message="Are you sure you want to UNFK? Once UNFK'd you cannot RFK"
          onConfirm={confirmUnfk}
          onCancel={() => {
            setShowUnfkConfirm(false)
            setItemToUnfk(null)
          }}
        />
      )}
    </div>
  )
}

export default ItemsList
