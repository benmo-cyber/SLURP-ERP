import { useState, useEffect } from 'react'
import { getFormulas, getItems } from '../../api/inventory'
import './Formulas.css'

function Formulas() {
  const [formulas, setFormulas] = useState<any[]>([])
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

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
              <th>Finished Good</th>
              <th>Version</th>
              <th>Ingredients</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {formulas.length === 0 ? (
              <tr>
                <td colSpan={4} className="empty-state">
                  No formulas found.
                </td>
              </tr>
            ) : (
              formulas.map((formula) => (
                <tr key={formula.id}>
                  <td>{formula.finished_good?.name || '-'}</td>
                  <td>{formula.version}</td>
                  <td>
                    {formula.ingredients?.length > 0
                      ? formula.ingredients.map((ing: any) => `${ing.item?.name} (${ing.percentage}%)`).join(', ')
                      : '-'}
                  </td>
                  <td>{new Date(formula.created_at).toLocaleDateString()}</td>
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

