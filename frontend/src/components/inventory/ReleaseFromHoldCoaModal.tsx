import { useState } from 'react'
import type { CoaReleasePreview, ItemCoaTestLine } from '../../api/coa'
import { releaseLotFromHold } from '../../api/inventory'
import './ReleaseFromHoldCoaModal.css'

type Props = {
  lotId: number
  lotLabel: string
  releaseQty: number
  preview: CoaReleasePreview
  onClose: () => void
  /** Serialized lot from release API (merge into local lot row). */
  onSuccess: (updatedLot: Record<string, unknown>) => void
}

function ReleaseFromHoldCoaModal({ lotId, lotLabel, releaseQty, preview, onClose, onSuccess }: Props) {
  const [qcValue, setQcValue] = useState('')
  const [lineValues, setLineValues] = useState<Record<number, string>>(() => {
    const m: Record<number, string> = {}
    for (const line of preview.template_lines) {
      m[line.id] = ''
    }
    return m
  })
  const [saving, setSaving] = useState(false)

  const setLine = (id: number, v: string) => {
    setLineValues((prev) => ({ ...prev, [id]: v }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const line_results = preview.template_lines.map((line: ItemCoaTestLine) => ({
      item_line_id: line.id,
      result_text: (lineValues[line.id] ?? '').trim(),
    }))
    for (const row of line_results) {
      if (!row.result_text) {
        alert(`Enter a result for: ${preview.template_lines.find((l) => l.id === row.item_line_id)?.test_name}`)
        return
      }
    }
    let qc_result_value: number | undefined
    if (preview.formula_qc) {
      const q = parseFloat(qcValue)
      if (Number.isNaN(q)) {
        alert(`Enter QC result for ${preview.formula_qc.qc_parameter_name}`)
        return
      }
      qc_result_value = q
    }

    try {
      setSaving(true)
      const updatedLot = await releaseLotFromHold(lotId, releaseQty, {
        qc_result_value,
        line_results,
      })
      onSuccess(updatedLot as Record<string, unknown>)
      onClose()
    } catch (err: any) {
      const d = err?.response?.data
      const msg =
        typeof d?.error === 'string'
          ? d.error
          : Array.isArray(d)
            ? d.join(', ')
            : d?.detail
              ? String(d.detail)
              : err?.message || 'Release failed'
      alert(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="release-coa-modal" onClick={(e) => e.stopPropagation()}>
        <div className="release-coa-modal__header">
          <h2>Micro &amp; QC — release from hold</h2>
          <button type="button" className="release-coa-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <p className="release-coa-modal__intro">
          Lot <strong>{lotLabel}</strong>: releasing <strong>{releaseQty}</strong> clears hold. This creates the{' '}
          <strong>master</strong> Certificate of Analysis (test results for the lot). Customer name and PO are filled in on
          separate COA PDFs when you <strong>allocate this lot on a sales order</strong> (from the order’s customer and
          customer reference / PO).
        </p>
        <form onSubmit={(e) => void handleSubmit(e)}>
          {preview.formula_qc && (
            <div className="release-coa-modal__qc">
              <h3>QC ({preview.formula_qc.qc_parameter_name})</h3>
              <p className="release-coa-modal__hint">
                Spec: min {preview.formula_qc.qc_spec_min ?? '—'} / max {preview.formula_qc.qc_spec_max ?? '—'}
              </p>
              <label>
                Result value
                <input type="number" step="any" value={qcValue} onChange={(e) => setQcValue(e.target.value)} required />
              </label>
            </div>
          )}

          {preview.template_lines.length > 0 && (
            <div className="release-coa-modal__lines">
              <h3>Micro / analysis lines</h3>
              <table className="release-coa-modal__table">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Specification</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.template_lines.map((line) => (
                    <tr key={line.id}>
                      <td>{line.test_name}</td>
                      <td className="release-coa-modal__spec">{line.specification_text}</td>
                      <td>
                        <input
                          value={lineValues[line.id] ?? ''}
                          onChange={(e) => setLine(line.id, e.target.value)}
                          placeholder={line.result_kind === 'pass_fail' ? 'Pass / Fail' : 'Value'}
                          required
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="release-coa-modal__actions">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save results & release'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ReleaseFromHoldCoaModal
