import { useState } from 'react'
import InventoryTable from '../components/inventory/InventoryTable'
import CheckInForm from '../components/inventory/CheckInForm'
import CreateItemForm from '../components/inventory/CreateItemForm'
import ReverseCheckIn from '../components/inventory/ReverseCheckIn'
import ItemsList from '../components/inventory/ItemsList'
import PurchaseOrderList from '../components/inventory/PurchaseOrderList'
import CreatePurchaseOrder from '../components/inventory/CreatePurchaseOrder'
import './Inventory.css'

function Inventory() {
  const [activeTab, setActiveTab] = useState<'inventory' | 'items' | 'purchase-orders'>('inventory')
  const [showCheckIn, setShowCheckIn] = useState(false)
  const [showCreateItem, setShowCreateItem] = useState(false)
  const [showReverseCheckIn, setShowReverseCheckIn] = useState(false)
  const [showCreatePO, setShowCreatePO] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCheckInSuccess = () => {
    setShowCheckIn(false)
    setRefreshKey(prev => prev + 1)
  }

  const handleCreateItemSuccess = () => {
    setShowCreateItem(false)
    setRefreshKey(prev => prev + 1)
  }

  const handleCreatePOSuccess = () => {
    setShowCreatePO(false)
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
        <button
          className={`tab-button ${activeTab === 'purchase-orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('purchase-orders')}
        >
          Purchase Orders
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
            <button onClick={() => setShowReverseCheckIn(true)} className="btn btn-danger">
              UNFK
            </button>
          </>
        )}
        {activeTab === 'purchase-orders' && (
          <button onClick={() => setShowCreatePO(true)} className="btn btn-primary">
            Create Purchase Order
          </button>
        )}
      </div>

      <div className="inventory-content">
        {activeTab === 'inventory' && <InventoryTable key={refreshKey} />}
        {activeTab === 'items' && <ItemsList />}
        {activeTab === 'purchase-orders' && <PurchaseOrderList key={refreshKey} />}
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
      {showReverseCheckIn && (
        <ReverseCheckIn
          onClose={() => setShowReverseCheckIn(false)}
          onSuccess={() => {
            setShowReverseCheckIn(false)
            setRefreshKey(prev => prev + 1)
          }}
        />
      )}
      {showCreatePO && (
        <CreatePurchaseOrder
          onClose={() => setShowCreatePO(false)}
          onSuccess={handleCreatePOSuccess}
        />
      )}
    </div>
  )
}

export default Inventory

