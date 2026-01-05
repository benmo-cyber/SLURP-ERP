import { useState, useEffect } from 'react'
import { getItems, createItem, updateItem, deleteItem } from '../../api/inventory'
import './Items.css'

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  item_type: 'raw_material' | 'distributed_item' | 'finished_good' | 'indirect_material'
  unit_of_measure: 'lbs' | 'kg' | 'ea'
  vendor?: string
  approved_for_formulas: boolean
  created_at: string
  updated_at: string
}

function Items() {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingItem, setEditingItem] = useState<Item | null>(null)
  const [formData, setFormData] = useState({
    sku: '',
    name: '',
    description: '',
    item_type: 'raw_material' as Item['item_type'],
    unit_of_measure: 'lbs' as Item['unit_of_measure'],
    vendor: '',
    approved_for_formulas: false,
  })

  useEffect(() => {
    loadItems()
  }, [])

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingItem) {
        await updateItem(editingItem.id, formData)
      } else {
        await createItem(formData)
      }
      await loadItems()
      resetForm()
    } catch (error) {
      console.error('Failed to save item:', error)
      alert('Failed to save item')
    }
  }

  const handleEdit = (item: Item) => {
    setEditingItem(item)
    setFormData({
      sku: item.sku,
      name: item.name,
      description: item.description || '',
      item_type: item.item_type,
      unit_of_measure: item.unit_of_measure,
      vendor: item.vendor || '',
      approved_for_formulas: item.approved_for_formulas,
    })
    setShowForm(true)
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this item?')) return
    try {
      await deleteItem(id)
      await loadItems()
    } catch (error) {
      console.error('Failed to delete item:', error)
      alert('Failed to delete item')
    }
  }

  const resetForm = () => {
    setFormData({
      sku: '',
      name: '',
      description: '',
      item_type: 'raw_material',
      unit_of_measure: 'lbs',
      vendor: '',
      approved_for_formulas: false,
    })
    setEditingItem(null)
    setShowForm(false)
  }

  if (loading) {
    return <div className="loading">Loading items...</div>
  }

  return (
    <div className="items-container">
      <div className="items-header">
        <h2>Items</h2>
        <button onClick={() => setShowForm(true)} className="btn btn-primary">
          + Add Item
        </button>
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={resetForm}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? 'Edit Item' : 'New Item'}</h3>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>SKU *</label>
                <input
                  type="text"
                  value={formData.sku}
                  onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                  required
                  disabled={!!editingItem}
                />
              </div>
              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Item Type *</label>
                  <select
                    value={formData.item_type}
                    onChange={(e) => setFormData({ ...formData, item_type: e.target.value as Item['item_type'] })}
                    required
                  >
                    <option value="raw_material">Raw Material</option>
                    <option value="distributed_item">Distributed Item</option>
                    <option value="finished_good">Finished Good</option>
                    <option value="indirect_material">Indirect Material</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Unit of Measure *</label>
                  <select
                    value={formData.unit_of_measure}
                    onChange={(e) => setFormData({ ...formData, unit_of_measure: e.target.value as Item['unit_of_measure'] })}
                    required
                  >
                    <option value="lbs">Pounds</option>
                    <option value="kg">Kilograms</option>
                    <option value="ea">Each</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>Vendor</label>
                <input
                  type="text"
                  value={formData.vendor}
                  onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.approved_for_formulas}
                    onChange={(e) => setFormData({ ...formData, approved_for_formulas: e.target.checked })}
                  />
                  Approved for Formulas
                </label>
              </div>
              <div className="form-actions">
                <button type="submit" className="btn btn-primary">
                  {editingItem ? 'Update' : 'Create'}
                </button>
                <button type="button" onClick={resetForm} className="btn btn-secondary">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="items-table-container">
        <table className="items-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Name</th>
              <th>Type</th>
              <th>Unit</th>
              <th>Vendor</th>
              <th>Formula Approved</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-state">
                  No items found. Click "Add Item" to create one.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id}>
                  <td>{item.sku}</td>
                  <td>{item.name}</td>
                  <td>
                    <span className="badge badge-type">{item.item_type.replace('_', ' ')}</span>
                  </td>
                  <td>{item.unit_of_measure}</td>
                  <td>{item.vendor || '-'}</td>
                  <td>{item.approved_for_formulas ? '✓' : '-'}</td>
                  <td>
                    <button onClick={() => handleEdit(item)} className="btn btn-sm btn-secondary">
                      Edit
                    </button>
                    <button onClick={() => handleDelete(item.id)} className="btn btn-sm btn-danger">
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Items

