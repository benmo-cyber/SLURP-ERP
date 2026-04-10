import { useState, useEffect } from 'react'
import { getFormulas, getItems } from '../../api/inventory'
import { formatAppDate } from '../../utils/appDateFormat'
import './Formulas.css'

type FormulaSortKey = 'finished_good' | 'version' | 'created' | null

function Formulas() {
  const [formulas, setFormulas] = useState<any[]>([])
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<{ key: FormulaSortKey; dir: 'asc' | 'desc' }>({ key: 'finished_good', dir: 'asc' })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [formulasData, itemsData] = await Promise.all([getFormulas(), getItems()])
      setFormulas(formulasData)
      setItems(itemsData)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const sortedFormulas = [...formulas].sort((a, b) => {
    if (!sort.key) return 0
    let cmp = 0
    switch (sort.key) {
      case 'finished_good':
        cmp = (a.finished_good?.name || '').localeCompare(b.finished_good?.name || '')
        break
      case 'version':
        cmp = (a.version ?? 0) - (b.version ?? 0)
        break
      case 'created':
        cmp = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime()
        break
      default:
        return 0
    }
    return sort.dir === 'asc' ? cmp : -cmp
  })

  const handleSort = (key: FormulaSortKey) => {
    setSort(prev => ({ key: key!, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  if (loading) {
    return <div className="loading">Loading formulas...</div>
  }

  return (
    <div className="formulas-container">
      <div className="formulas-header">
        <h2>Formulas</h2>
        <button className="btn btn-primary">+ Add Formula</button>
      </div>

      <div className="formulas-table-container">
        <table className="formulas-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => handleSort('finished_good')}>Finished Good {sort.key === 'finished_good' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('version')}>Version {sort.key === 'version' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>Ingredients</th>
              <th className="sortable" onClick={() => handleSort('created')}>Created {sort.key === 'created' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
            </tr>
          </thead>
          <tbody>
            {sortedFormulas.length === 0 ? (
              <tr>
                <td colSpan={4} className="empty-state">
                  No formulas found.
                </td>
              </tr>
            ) : (
              sortedFormulas.map((formula) => (
                <tr key={formula.id}>
                  <td>{formula.finished_good?.name || '-'}</td>
                  <td>{formula.version}</td>
                  <td>
                    {formula.ingredients?.length > 0
                      ? formula.ingredients.map((ing: any) => `${ing.item?.name} (${ing.percentage}%)`).join(', ')
                      : '-'}
                  </td>
                  <td>{formatAppDate(formula.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Formulas

