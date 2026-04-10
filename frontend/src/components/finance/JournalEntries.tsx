import { useState, useEffect } from 'react'
import { getJournalEntries } from '../../api/finance'
import CreateJournalEntry from './CreateJournalEntry'
import { formatAppDate } from '../../utils/appDateFormat'
import './JournalEntries.css'

type EntrySortKey = 'entry_number' | 'entry_date' | 'description' | 'reference_number' | 'created_at' | null

function JournalEntries() {
  const [entries, setEntries] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sort, setSort] = useState<{ key: EntrySortKey; dir: 'asc' | 'desc' }>({ key: 'entry_date', dir: 'desc' })

  useEffect(() => {
    loadEntries()
  }, [refreshKey])

  const sortedEntries = [...entries].sort((a, b) => {
    if (!sort.key) return 0
    let cmp = 0
    switch (sort.key) {
      case 'entry_number': cmp = (a.entry_number || '').localeCompare(b.entry_number || ''); break
      case 'entry_date': cmp = new Date(a.entry_date).getTime() - new Date(b.entry_date).getTime(); break
      case 'description': cmp = (a.description || '').localeCompare(b.description || ''); break
      case 'reference_number': cmp = (a.reference_number || '').localeCompare(b.reference_number || ''); break
      case 'created_at': cmp = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime(); break
      default: return 0
    }
    return sort.dir === 'asc' ? cmp : -cmp
  })
  const handleSort = (key: NonNullable<EntrySortKey>) => {
    setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  const loadEntries = async () => {
    try {
      setLoading(true)
      const data = await getJournalEntries()
      setEntries(data)
    } catch (error) {
      console.error('Failed to load journal entries:', error)
      alert('Failed to load journal entries')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSuccess = () => {
    setShowCreate(false)
    setRefreshKey(prev => prev + 1)
  }

  if (loading) {
    return <div className="loading">Loading journal entries...</div>
  }

  return (
    <div className="journal-entries">
      <div className="entries-header">
        <h2>Journal Entries</h2>
        <button onClick={() => setShowCreate(true)} className="btn btn-primary">
          + Create Journal Entry
        </button>
      </div>

      <div className="entries-table-container">
        <table className="entries-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => handleSort('entry_number')}>Entry Number {sort.key === 'entry_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('entry_date')}>Date {sort.key === 'entry_date' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('description')}>Description {sort.key === 'description' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th className="sortable" onClick={() => handleSort('reference_number')}>Reference {sort.key === 'reference_number' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
              <th>Lines</th>
              <th className="sortable" onClick={() => handleSort('created_at')}>Created {sort.key === 'created_at' && (sort.dir === 'asc' ? '↑' : '↓')}</th>
            </tr>
          </thead>
          <tbody>
            {sortedEntries.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  No journal entries found. Click "Create Journal Entry" to add one.
                </td>
              </tr>
            ) : (
              sortedEntries.map((entry) => (
                <tr key={entry.id}>
                  <td className="entry-number">{entry.entry_number}</td>
                  <td>{formatAppDate(entry.entry_date)}</td>
                  <td>{entry.description}</td>
                  <td>{entry.reference_number || '-'}</td>
                  <td>{entry.lines?.length || 0} lines</td>
                  <td>{formatAppDate(entry.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateJournalEntry
          onClose={() => setShowCreate(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  )
}

export default JournalEntries






