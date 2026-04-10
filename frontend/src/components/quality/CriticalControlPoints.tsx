import { useState, useEffect } from 'react'
import {
  getCriticalControlPoints,
  createCriticalControlPoint,
  updateCriticalControlPoint,
  deleteCriticalControlPoint,
} from '../../api/inventory'
import ConfirmDialog from '../common/ConfirmDialog'
import './CriticalControlPoints.css'

interface CCP {
  id: number
  name: string
  display_order: number
}

function CriticalControlPoints() {
  const [list, setList] = useState<CCP[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [addName, setAddName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<CCP | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const data = await getCriticalControlPoints()
      setList(data)
    } catch (error) {
      console.error('Failed to load CCPs:', error)
      alert('Failed to load critical control points')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const startEdit = (ccp: CCP) => {
    setEditingId(ccp.id)
    setEditName(ccp.name)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditName('')
  }

  const saveEdit = async () => {
    if (editingId == null || !editName.trim()) return
    try {
      setSubmitting(true)
      await updateCriticalControlPoint(editingId, { name: editName.trim() })
      await load()
      cancelEdit()
    } catch (error: any) {
      console.error('Failed to update CCP:', error)
      alert(error.response?.data?.name?.[0] || error.message || 'Failed to update')
    } finally {
      setSubmitting(false)
    }
  }

  const handleAdd = async () => {
    if (!addName.trim()) return
    try {
      setSubmitting(true)
      await createCriticalControlPoint({ name: addName.trim() })
      await load()
      setShowAdd(false)
      setAddName('')
    } catch (error: any) {
      console.error('Failed to add CCP:', error)
      alert(error.response?.data?.name?.[0] || error.message || 'Failed to add')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return
    try {
      setSubmitting(true)
      await deleteCriticalControlPoint(deleteConfirm.id)
      await load()
      setDeleteConfirm(null)
    } catch (error: any) {
      console.error('Failed to delete CCP:', error)
      alert(error.response?.data?.detail || error.message || 'Failed to delete. It may be in use by a formula.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="ccp-loading">Loading critical control points...</div>
  }

  return (
    <div className="critical-control-points">
      <div className="ccp-header">
        <div>
          <h2>Critical Control Points (CCPs)</h2>
          <p className="ccp-description">
            CCPs appear on batch ticket pre-production checks: &quot;Has [CCP] been inspected and installed properly?&quot;
            Assign a CCP to a finished good when creating it or in Edit Formula.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => { setShowAdd(true); setAddName('') }}
        >
          + Add CCP
        </button>
      </div>

      {showAdd && (
        <div className="ccp-add-row">
          <input
            type="text"
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            placeholder="e.g. 20 mesh screen, 40 mesh screen"
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          />
          <button type="button" className="btn btn-primary" onClick={handleAdd} disabled={submitting || !addName.trim()}>
            Save
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => { setShowAdd(false); setAddName('') }}>
            Cancel
          </button>
        </div>
      )}

      <div className="ccp-card">
        <table className="ccp-table">
          <thead>
            <tr>
              <th>Name</th>
              <th style={{ width: '160px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 && !showAdd && (
              <tr>
                <td colSpan={2} className="ccp-empty">No CCPs yet. Add one to use on formulas and batch tickets.</td>
              </tr>
            )}
            {list.map((ccp) => (
              <tr key={ccp.id}>
                <td>
                  {editingId === ccp.id ? (
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
                    />
                  ) : (
                    ccp.name
                  )}
                </td>
                <td>
                  <div className="ccp-actions">
                    {editingId === ccp.id ? (
                      <>
                        <button type="button" className="btn btn-primary btn-sm" onClick={saveEdit} disabled={submitting || !editName.trim()}>
                          Save
                        </button>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={cancelEdit}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => startEdit(ccp)}>Edit</button>
                        <button type="button" className="btn btn-danger btn-sm" onClick={() => setDeleteConfirm(ccp)}>Delete</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {deleteConfirm && (
        <ConfirmDialog
          message={`Delete "${deleteConfirm.name}"? Formulas using it will have no CCP on batch tickets until you pick another.`}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  )
}

export default CriticalControlPoints
