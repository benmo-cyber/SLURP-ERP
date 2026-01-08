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
      alert(error.response?.data?.detail || 'Failed to reverse batch ticket')
    } finally {
      setBatchToUnfk(null)
    }
  }

  return (
    <div className="production-page">
      <div className="page-header">
        <h1>Production</h1>
        <div className="header-actions">
          <button onClick={() => setShowCreateBatch(true)} className="btn btn-primary">
            Create Batch Ticket
          </button>
        </div>
      </div>

      <div className="page-content">
        <ProductionBatchList 
          key={refreshKey}
          onCloseBatch={handleCloseBatch}
          onUnfkBatch={handleUnfkBatch}
          onAdjustBatch={handleAdjustBatch}
        />
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
          message="Are you sure you want to UNFK? Once UNFK'd you cannot RFK"
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

