import { useState, useEffect } from 'react'
import { getItems, getFormulas } from '../../api/inventory'
import CreateFinishedGood from './CreateFinishedGood'
import UnlinkFinishedGood from './UnlinkFinishedGood'
import EditFormula from './EditFormula'
import ItemCoaTestLinesEditor from './ItemCoaTestLinesEditor'
import { formatAppDate } from '../../utils/appDateFormat'
import './FinishedGoodsList.css'

interface Item {
  id: number
  sku: string
  name: string
  description?: string
  item_type: string
  vendor?: string | null
  unit_of_measure: string
  pack_size?: number
  created_at: string
  updated_at: string
}

function itemTypeLabel(itemType: string): string {
  if (itemType === 'distributed_item') return 'Distributed'
  if (itemType === 'finished_good') return 'Finished good'
  return itemType
}

function formatVendor(v: string | null | undefined): string {
  const s = (v || '').trim()
  return s || '—'
}

function FinishedGoodsList() {
  const [finishedGoods, setFinishedGoods] = useState<Item[]>([])
  const [formulas, setFormulas] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [showUnlinkModal, setShowUnlinkModal] = useState(false)
  const [editingFormula, setEditingFormula] = useState<{itemId: number, sku: string, name: string} | null>(null)
  const [coaEditorItem, setCoaEditorItem] = useState<Item | null>(null)

  useEffect(() => {
    loadFinishedGoods()
  }, [])

  const loadFinishedGoods = async () => {
    try {
      setLoading(true)
      const [items, formulasData] = await Promise.all([
        getItems(),
        getFormulas()
      ])
      const finishedGoods = items
        .filter((item: Item) => item.item_type === 'finished_good' || item.item_type === 'distributed_item')
        .sort((a, b) => {
          const sku = (a.sku || '').localeCompare(b.sku || '')
          if (sku !== 0) return sku
          const va = (a.vendor || '').trim()
          const vb = (b.vendor || '').trim()
          return va.localeCompare(vb)
        })
      setFinishedGoods(finishedGoods)
      setFormulas(formulasData)
    } catch (error) {
      console.error('Failed to load finished goods:', error)
      alert('Failed to load finished goods')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSuccess = () => {
    setShowCreateForm(false)
    loadFinishedGoods()
  }

  const handleUnlinkSuccess = () => {
    setShowUnlinkModal(false)
    loadFinishedGoods()
  }

  const handleEditSuccess = () => {
    setEditingFormula(null)
    loadFinishedGoods()
  }

  const handleEditFormula = (item: Item) => {
    setEditingFormula({
      itemId: item.id,
      sku: item.sku,
      name: item.name
    })
  }

  if (loading) {
    return <div className="loading">Loading finished goods...</div>
  }

  return (
    <div className="finished-goods-list">
      <div className="finished-goods-header">
        <div>
          <h2>Finished Goods</h2>
          <p className="finished-goods-subtitle">
            Same SKU can appear twice: each row is a separate item keyed by <strong>SKU + vendor</strong> (e.g. in-house
            manufacture vs a vendor). Distributed SKUs are listed here so COA / micro test lines can be set per item.
          </p>
        </div>
        <div className="header-actions">
          <button 
            onClick={() => setShowCreateForm(true)} 
            className="btn btn-primary"
          >
            Create Finished Good
          </button>
          <button
            onClick={() => setShowUnlinkModal(true)}
            className="btn btn-danger"
            title="Remove a finished good from the catalog (not a batch or receipt reversal)"
          >
            Unlink finished good
          </button>
        </div>
      </div>

      {showCreateForm && (
        <div className="modal-overlay" onClick={() => setShowCreateForm(false)}>
          <div className="modal-content finished-good-modal" onClick={(e) => e.stopPropagation()}>
            <CreateFinishedGood 
              onClose={() => setShowCreateForm(false)} 
              onSuccess={handleCreateSuccess} 
            />
          </div>
        </div>
      )}

      {showUnlinkModal && (
        <UnlinkFinishedGood
          onClose={() => setShowUnlinkModal(false)}
          onSuccess={handleUnlinkSuccess}
        />
      )}

      {editingFormula && (
        <div className="modal-overlay" onClick={() => setEditingFormula(null)}>
          <div className="modal-content finished-good-modal" onClick={(e) => e.stopPropagation()}>
            <EditFormula
              finishedGoodId={editingFormula.itemId}
              finishedGoodSku={editingFormula.sku}
              finishedGoodName={editingFormula.name}
              onClose={() => setEditingFormula(null)}
              onSuccess={handleEditSuccess}
            />
          </div>
        </div>
      )}

      {coaEditorItem && (
        <div className="modal-overlay" onClick={() => setCoaEditorItem(null)}>
          <div className="modal-content finished-good-modal coa-lines-modal-wrap" onClick={(e) => e.stopPropagation()}>
            <ItemCoaTestLinesEditor
              itemId={coaEditorItem.id}
              sku={coaEditorItem.sku}
              name={coaEditorItem.name}
              onClose={() => setCoaEditorItem(null)}
            />
          </div>
        </div>
      )}

      <div className="finished-goods-table-wrapper">
        <table className="finished-goods-table">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Type</th>
              <th>Vendor</th>
              <th>Name</th>
              <th>Description</th>
              <th>Unit of Measure</th>
              <th>Pack Size</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {finishedGoods.length === 0 ? (
              <tr>
                <td colSpan={9} className="empty-state">
                  No finished goods found. Click "Create Finished Good" to add one.
                </td>
              </tr>
            ) : (
              finishedGoods.map((item) => {
                const hasFormula = formulas.some(f => f.finished_good?.id === item.id)
                return (
                  <tr key={item.id}>
                    <td><strong>{item.sku}</strong></td>
                    <td>
                      <span
                        className={
                          item.item_type === 'distributed_item'
                            ? 'finished-goods-type-badge finished-goods-type-badge--distributed'
                            : 'finished-goods-type-badge'
                        }
                      >
                        {itemTypeLabel(item.item_type)}
                      </span>
                    </td>
                    <td>{formatVendor(item.vendor)}</td>
                    <td>{item.name}</td>
                    <td>{item.description || '-'}</td>
                    <td>{item.unit_of_measure}</td>
                    <td>{item.pack_size ? `${item.pack_size} ${item.unit_of_measure}` : '-'}</td>
                    <td>{formatAppDate(item.created_at)}</td>
                    <td>
                      <div className="finished-goods-actions">
                        {hasFormula ? (
                          <button
                            type="button"
                            onClick={() => handleEditFormula(item)}
                            className="btn btn-sm btn-secondary"
                            style={{ padding: '4px 12px', fontSize: '0.875rem' }}
                          >
                            Edit Formula
                          </button>
                        ) : (
                          <span style={{ color: '#999', fontStyle: 'italic' }}>No formula</span>
                        )}
                        <button
                          type="button"
                          onClick={() => setCoaEditorItem(item)}
                          className="btn btn-sm btn-secondary"
                          style={{ padding: '4px 12px', fontSize: '0.875rem' }}
                          title="Micro tests and COA specification rows for this SKU"
                        >
                          COA / micro tests
                        </button>
                      </div>
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

export default FinishedGoodsList
