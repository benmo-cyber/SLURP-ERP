import { useState, useEffect } from 'react'
import {
  getItemCoaTestLines,
  createItemCoaTestLine,
  updateItemCoaTestLine,
  deleteItemCoaTestLine,
  type ItemCoaTestLine,
} from '../../api/coa'
import './ItemCoaTestLinesEditor.css'

const RESULT_KINDS: { value: ItemCoaTestLine['result_kind']; label: string }[] = [
  { value: 'text_only', label: 'Text only' },
  { value: 'pass_fail', label: 'Pass / fail' },
  { value: 'numeric_minimum', label: 'Numeric minimum (e.g. NLT)' },
  { value: 'numeric_range', label: 'Numeric range (min–max)' },
]

type Props = {
  itemId: number
  sku: string
  name: string
  onClose: () => void
  onSaved?: () => void
}

function ItemCoaTestLinesEditor({ itemId, sku, name, onClose, onSaved }: Props) {
  const [lines, setLines] = useState<ItemCoaTestLine[]>([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | 'new' | null>(null)

  const load = async () => {
    try {
      setLoading(true)
      const data = await getItemCoaTestLines(itemId)
      setLines(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error(e)
      alert('Failed to load COA test lines')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [itemId])

  const addRow = () => {
    const maxOrder = lines.reduce((m, l) => Math.max(m, l.sort_order), -1)
    setLines([
      ...lines,
      {
        id: -Date.now(),
        item: itemId,
        sort_order: maxOrder + 1,
        test_name: '',
        specification_text: '',
        result_kind: 'pass_fail',
        numeric_min: null,
        numeric_max: null,
      },
    ])
  }

  const updateLocal = (id: number, patch: Partial<ItemCoaTestLine>) => {
    setLines((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  }

  const saveLine = async (line: ItemCoaTestLine) => {
    const tn = line.test_name.trim()
    const spec = line.specification_text.trim()
    if (!tn || !spec) {
      alert('Test name and specification are required')
      return
    }
    const isNew = line.id < 0
    try {
      setSavingId(isNew ? 'new' : line.id)
      if (isNew) {
        await createItemCoaTestLine({
          item: itemId,
          sort_order: line.sort_order,
          test_name: tn,
          specification_text: spec,
          result_kind: line.result_kind,
          numeric_min: line.numeric_min,
          numeric_max: line.numeric_max,
        })
      } else {
        await updateItemCoaTestLine(line.id, {
          sort_order: line.sort_order,
          test_name: tn,
          specification_text: spec,
          result_kind: line.result_kind,
          numeric_min: line.numeric_min,
          numeric_max: line.numeric_max,
        })
      }
      await load()
      onSaved?.()
    } catch (e: any) {
      console.error(e)
      const d = e?.response?.data
      alert(typeof d === 'object' ? JSON.stringify(d) : e?.message || 'Save failed')
    } finally {
      setSavingId(null)
    }
  }

  const removeLine = async (line: ItemCoaTestLine) => {
    if (line.id < 0) {
      setLines((prev) => prev.filter((l) => l.id !== line.id))
      return
    }
    if (!window.confirm(`Delete test line "${line.test_name}"?`)) return
    try {
      await deleteItemCoaTestLine(line.id)
      await load()
      onSaved?.()
    } catch (e) {
      console.error(e)
      alert('Delete failed')
    }
  }

  return (
    <div className="item-coa-editor" onClick={(e) => e.stopPropagation()}>
      <div className="item-coa-editor__header">
        <div>
          <h2>COA / micro tests</h2>
          <p className="item-coa-editor__sub">
            <strong>{sku}</strong> — {name}
          </p>
          <p className="item-coa-editor__hint">
            These rows appear on the Certificate of Analysis when the lot is fully released from hold. Match specification
            text to what appears on the COA (e.g. NLT 0.7%, &lt;1000/g).
          </p>
        </div>
        <button type="button" className="item-coa-editor__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      {loading ? (
        <div className="item-coa-editor__loading">Loading…</div>
      ) : (
        <>
          <div className="item-coa-editor__toolbar">
            <button type="button" className="btn btn-primary btn-sm" onClick={addRow}>
              Add test line
            </button>
          </div>
          <div className="item-coa-editor__table-wrap">
            <table className="item-coa-editor__table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Test</th>
                  <th>Specification</th>
                  <th>Result type</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="item-coa-editor__empty">
                      No lines yet. Add tests (e.g. % Betanin, TPC, Yeast and Mold).
                    </td>
                  </tr>
                ) : (
                  lines.map((line) => (
                    <tr key={line.id}>
                      <td>
                        <input
                          type="number"
                          className="item-coa-editor__input item-coa-editor__input--narrow"
                          value={line.sort_order}
                          onChange={(e) =>
                            updateLocal(line.id, { sort_order: parseInt(e.target.value, 10) || 0 })
                          }
                        />
                      </td>
                      <td>
                        <input
                          className="item-coa-editor__input"
                          value={line.test_name}
                          onChange={(e) => updateLocal(line.id, { test_name: e.target.value })}
                          placeholder="e.g. TPC"
                        />
                      </td>
                      <td>
                        <input
                          className="item-coa-editor__input"
                          value={line.specification_text}
                          onChange={(e) => updateLocal(line.id, { specification_text: e.target.value })}
                          placeholder="e.g. &lt;1000/g"
                        />
                      </td>
                      <td>
                        <select
                          className="item-coa-editor__select"
                          value={line.result_kind}
                          onChange={(e) =>
                            updateLocal(line.id, { result_kind: e.target.value as ItemCoaTestLine['result_kind'] })
                          }
                        >
                          {RESULT_KINDS.map((k) => (
                            <option key={k.value} value={k.value}>
                              {k.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          step="any"
                          className="item-coa-editor__input item-coa-editor__input--narrow"
                          value={line.numeric_min ?? ''}
                          onChange={(e) =>
                            updateLocal(line.id, {
                              numeric_min: e.target.value === '' ? null : parseFloat(e.target.value),
                            })
                          }
                          disabled={line.result_kind === 'pass_fail' || line.result_kind === 'text_only'}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="any"
                          className="item-coa-editor__input item-coa-editor__input--narrow"
                          value={line.numeric_max ?? ''}
                          onChange={(e) =>
                            updateLocal(line.id, {
                              numeric_max: e.target.value === '' ? null : parseFloat(e.target.value),
                            })
                          }
                          disabled={line.result_kind !== 'numeric_range'}
                        />
                      </td>
                      <td className="item-coa-editor__actions">
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          disabled={savingId !== null}
                          onClick={() => void saveLine(line)}
                        >
                          {savingId === line.id || (line.id < 0 && savingId === 'new') ? '…' : 'Save'}
                        </button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => void removeLine(line)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
      <div className="item-coa-editor__footer">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

export default ItemCoaTestLinesEditor
