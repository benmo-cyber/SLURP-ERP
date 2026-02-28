import React, { useState, useEffect } from 'react'
import { getFiscalPeriods, closeFiscalPeriod } from '../../api/finance'
import './FiscalPeriods.css'

interface FiscalPeriodType {
  id: number
  period_name: string
  start_date: string
  end_date: string
  is_closed: boolean
  closed_date: string | null
  closed_by: string | null
}

const FiscalPeriods: React.FC = () => {
  const [periods, setPeriods] = useState<FiscalPeriodType[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { load() }, [])

  const load = async () => {
    try {
      setLoading(true)
      const data = await getFiscalPeriods()
      setPeriods(Array.isArray(data) ? data : (data?.results || []))
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleClose = async (id: number) => {
    if (!confirm('Close this period? No further posting will be allowed for it.')) return
    try {
      await closeFiscalPeriod(id)
      load()
    } catch (err: any) {
      alert(err.response?.data?.error || err.response?.data?.detail || 'Failed to close period')
    }
  }

  const formatDate = (d: string) => d ? new Date(d).toLocaleDateString() : ''

  return (
    <div className="fiscal-periods">
      <h2>Fiscal Periods</h2>
      <p className="fiscal-periods-desc">Close a period to lock it; no new journal entries can be posted to a closed period.</p>
      {loading ? <p>Loading…</p> : (
        <table className="fiscal-periods-table">
          <thead>
            <tr>
              <th>Period</th>
              <th>Start</th>
              <th>End</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {periods.map(p => (
              <tr key={p.id}>
                <td>{p.period_name}</td>
                <td>{formatDate(p.start_date)}</td>
                <td>{formatDate(p.end_date)}</td>
                <td>{p.is_closed ? <span className="badge closed">Closed</span> : <span className="badge open">Open</span>}</td>
                <td>
                  {!p.is_closed && <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleClose(p.id)}>Close period</button>}
                  {p.is_closed && p.closed_by && <span className="closed-by">by {p.closed_by}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default FiscalPeriods
