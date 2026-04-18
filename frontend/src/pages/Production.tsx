import { useState } from 'react'
import ProductionBatchList from '../components/production/ProductionBatchList'
import CreateBatchTicket from '../components/production/CreateBatchTicket'
import CloseBatch from '../components/production/CloseBatch'
import AdjustBatch from '../components/production/AdjustBatch'
import ConfirmDialog from '../components/common/ConfirmDialog'
import './Production.css'

function Production() {
  const [showCreateBatch, setShowCreateBatch] = useState(false)
  const [showCloseBatch, setShowCloseBatch] = useState(false)
  const [showAdjustBatch, setShowAdjustBatch] = useState(false)
  const [selectedBatch, setSelectedBatch] = useState<any>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [showUnfkConfirm, setShowUnfkConfirm] = useState(false)
  const [batchToUnfk, setBatchToUnfk] = useState<any>(null)

  const handleCreateSuccess = () => {
    setShowCreateBatch(false)
    setRefreshKey(prev => prev + 1)
  }

  const handleCloseBatch = (batch: any) => {
    setSelectedBatch(batch)
    setShowCloseBatch(true)
  }

  const handleCloseSuccess = () => {
    setShowCloseBatch(false)
    setSelectedBatch(null)
    setRefreshKey(prev => prev + 1)
  }

  const handleAdjustBatch = (batch: any) => {
    setSelectedBatch(batch)
    setShowAdjustBatch(true)
  }

  const handleAdjustSuccess = () => {
    setShowAdjustBatch(false)
    setSelectedBatch(null)
    setRefreshKey(prev => prev + 1)
  }

  const handleUnfkBatch = (batch: any) => {
    setBatchToUnfk(batch)
    setShowUnfkConfirm(true)
  }

  const confirmUnfk = async () => {
    if (!batchToUnfk) return

    setShowUnfkConfirm(false)

    try {
      const { reverseBatchTicket } = await import('../api/inventory')
      await reverseBatchTicket(batchToUnfk.id)
      alert('Batch ticket reversed successfully')
      setRefreshKey(prev => prev + 1)
    } catch (error: any) {
      console.error('Failed to reverse batch:', error)
      console.error('Error response:', error.response)
      console.error('Error data:', error.response?.data)
      const data = error.response?.data
      const blockers = data?.blockers
      if (Array.isArray(blockers) && blockers.length > 0) {
        const lines = blockers.map((b: { message?: string }) => b.message || JSON.stringify(b)).join('\n\n')
        alert(`${data?.error || 'Cannot reverse this batch.'}\n\n${lines}`)
      } else {
        const errorMsg =
          data?.error || data?.detail || error.message || 'Failed to reverse batch ticket'
        alert(errorMsg)
      }
    } finally {
      setBatchToUnfk(null)
    }
  }

  return (
    <div className="production-page">
      <header className="production-header">
        <h1>Production</h1>
        <div className="production-header-actions">
          <button onClick={() => setShowCreateBatch(true)} className="btn btn-primary">
            Create Batch Ticket
          </button>
        </div>
      </header>

      <div className="production-layout">
        <nav className="production-sidebar">
          <div className="production-nav-section">
            <div className="production-nav-section-label">Production</div>
            <ul className="production-nav-list">
              <li>
                <button type="button" className="production-nav-item active">
                  Batch Tickets
                </button>
              </li>
            </ul>
          </div>
        </nav>

        <main className="production-main">
          <ProductionBatchList
            key={refreshKey}
            onCloseBatch={handleCloseBatch}
            onReverseBatch={handleUnfkBatch}
            onAdjustBatch={handleAdjustBatch}
          />
        </main>
      </div>

      {showCreateBatch && (
        <CreateBatchTicket
          onClose={() => setShowCreateBatch(false)}
          onSuccess={handleCreateSuccess}
        />
      )}

      {showCloseBatch && selectedBatch && (
        <CloseBatch
          batch={selectedBatch}
          onClose={() => {
            setShowCloseBatch(false)
            setSelectedBatch(null)
          }}
          onSuccess={handleCloseSuccess}
        />
      )}

      {showAdjustBatch && selectedBatch && (
        <AdjustBatch
          batch={selectedBatch}
          onClose={() => {
            setShowAdjustBatch(false)
            setSelectedBatch(null)
          }}
          onSuccess={handleAdjustSuccess}
        />
      )}

      {showUnfkConfirm && (
        <ConfirmDialog
          message="Reverse this batch ticket? Inventory changes from this batch will be rolled back and the batch will be removed. This cannot be undone."
          onConfirm={confirmUnfk}
          onCancel={() => {
            setShowUnfkConfirm(false)
            setBatchToUnfk(null)
          }}
        />
      )}
    </div>
  )
}

export default Production

