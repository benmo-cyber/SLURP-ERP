import { useState } from 'react'
import InventoryTable from '../components/inventory/InventoryTable'
import CheckInForm from '../components/inventory/CheckInForm'
import CreateItemForm from '../components/inventory/CreateItemForm'
import UnlinkItem from '../components/inventory/UnlinkItem'
import ItemsList from '../components/inventory/ItemsList'
import './Inventory.css'

function Inventory() {
  const [activeTab, setActiveTab] = useState<'inventory' | 'items'>('inventory')
  const [showCheckIn, setShowCheckIn] = useState(false)
  const [showCreateItem, setShowCreateItem] = useState(false)
  const [showUnlinkModal, setShowUnlinkModal] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCheckInSuccess = () => {
    setShowCheckIn(false)
    setRefreshKey(prev => prev + 1)
  }

  const handleCreateItemSuccess = () => {
    setShowCreateItem(false)
    setRefreshKey(prev => prev + 1)
  }

  return (
    <div className="inventory-page">
      <div className="inventory-header">
        <h1>Inventory</h1>
      </div>
      <div className="inventory-tabs">
        <button
          className={`tab-button ${activeTab === 'inventory' ? 'active' : ''}`}
          onClick={() => setActiveTab('inventory')}
        >
          Inventory Table
        </button>
        <button
          className={`tab-button ${activeTab === 'items' ? 'active' : ''}`}
          onClick={() => setActiveTab('items')}
        >
          Items Management
        </button>
      </div>
      <div className="inventory-actions">
        {activeTab === 'inventory' && (
          <>
            <button onClick={() => setShowCheckIn(true)} className="btn btn-primary">
              Check-In
            </button>
            <button onClick={() => setShowCreateItem(true)} className="btn btn-primary">
              Create New Item
            </button>
            <button onClick={() => setShowUnlinkModal(true)} className="btn btn-danger">
              UNFK
            </button>
          </>
        )}
      </div>

      <div className="inventory-content">
        {activeTab === 'inventory' && <InventoryTable key={refreshKey} />}
        {activeTab === 'items' && <ItemsList />}
      </div>

      {showCheckIn && (
        <CheckInForm
          onClose={() => setShowCheckIn(false)}
          onSuccess={handleCheckInSuccess}
        />
      )}

      {showCreateItem && (
        <CreateItemForm
          onClose={() => setShowCreateItem(false)}
          onSuccess={handleCreateItemSuccess}
        />
      )}
      {showUnlinkModal && (
        <UnlinkItem
          onClose={() => setShowUnlinkModal(false)}
          onSuccess={() => {
            setShowUnlinkModal(false)
            setRefreshKey(prev => prev + 1)
          }}
        />
      )}
    </div>
  )
}

export default Inventory

