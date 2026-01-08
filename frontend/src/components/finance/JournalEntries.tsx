import { useState, useEffect } from 'react'
import { getJournalEntries } from '../../api/finance'
import CreateJournalEntry from './CreateJournalEntry'
import './JournalEntries.css'

function JournalEntries() {
  const [entries, setEntries] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    loadEntries()
  }, [refreshKey])

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
              <th>Entry Number</th>
              <th>Date</th>
              <th>Description</th>
              <th>Reference</th>
              <th>Lines</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-state">
                  No journal entries found. Click "Create Journal Entry" to add one.
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <tr key={entry.id}>
                  <td className="entry-number">{entry.entry_number}</td>
                  <td>{new Date(entry.entry_date).toLocaleDateString()}</td>
                  <td>{entry.description}</td>
                  <td>{entry.reference_number || '-'}</td>
                  <td>{entry.lines?.length || 0} lines</td>
                  <td>{new Date(entry.created_at).toLocaleDateString()}</td>
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






