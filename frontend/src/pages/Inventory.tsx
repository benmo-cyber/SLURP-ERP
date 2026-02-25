import { useState } from 'react'
import InventoryTable from '../components/inventory/InventoryTable'
import CheckInForm from '../components/inventory/CheckInForm'
import CreateItemForm from '../components/inventory/CreateItemForm'
import ReverseCheckIn from '../components/inventory/ReverseCheckIn'
import ItemsList from '../components/inventory/ItemsList'
import PurchaseOrderList from '../components/inventory/PurchaseOrderList'
import CreatePurchaseOrder from '../components/inventory/CreatePurchaseOrder'
import IndirectMaterialCheckout from '../components/inventory/IndirectMaterialCheckout'
import Logs from '../components/inventory/Logs'
import './Inventory.css'

export type InventoryTabId = 'inventory' | 'items' | 'purchase-orders' | 'logs'

const NAV_SECTIONS: { label: string; items: { id: InventoryTabId; label: string }[] }[] = [
  { label: 'Stock', items: [{ id: 'inventory', label: 'Inventory Table' }] },
  { label: 'Items', items: [{ id: 'items', label: 'Items Management' }] },
  { label: 'Purchasing', items: [{ id: 'purchase-orders', label: 'Purchase Orders' }] },
  { label: 'Activity', items: [{ id: 'logs', label: 'Logs' }] },
]

function Inventory() {
  const [activeTab, setActiveTab] = useState<InventoryTabId>('inventory')
  const [showCheckIn, setShowCheckIn] = useState(false)
  const [showCreateItem, setShowCreateItem] = useState(false)
  const [showReverseCheckIn, setShowReverseCheckIn] = useState(false)
  const [showCreatePO, setShowCreatePO] = useState(false)
  const [showIndirectMaterialCheckout, setShowIndirectMaterialCheckout] = useState(false)
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
      <header className="inventory-header">
        <h1>Inventory</h1>
        {activeTab === 'inventory' && (
          <div className="inventory-header-actions">
            <button onClick={() => setShowCheckIn(true)} className="btn btn-primary">
              Check-In
            </button>
            <button onClick={() => setShowIndirectMaterialCheckout(true)} className="btn btn-primary">
              Checkout Indirect Material
            </button>
            <button onClick={() => setShowReverseCheckIn(true)} className="btn btn-danger">
              UNFK
            </button>
          </div>
        )}
        {activeTab === 'items' && (
          <div className="inventory-header-actions">
            <button onClick={() => setShowCreateItem(true)} className="btn btn-primary">
              Create New Item
            </button>
          </div>
        )}
        {activeTab === 'purchase-orders' && (
          <div className="inventory-header-actions">
            <button onClick={() => setShowCreatePO(true)} className="btn btn-primary">
              Create Purchase Order
            </button>
          </div>
        )}
      </header>

      <div className="inventory-layout">
        <nav className="inventory-sidebar">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="inventory-nav-section">
              <div className="inventory-nav-section-label">{section.label}</div>
              <ul className="inventory-nav-list">
                {section.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`inventory-nav-item ${activeTab === item.id ? 'active' : ''}`}
                      onClick={() => setActiveTab(item.id)}
                    >
                      {item.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <main className="inventory-main">
          {activeTab === 'inventory' && <InventoryTable key={refreshKey} />}
          {activeTab === 'items' && <ItemsList />}
          {activeTab === 'purchase-orders' && <PurchaseOrderList key={refreshKey} />}
          {activeTab === 'logs' && <Logs />}
        </main>
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
      {showIndirectMaterialCheckout && (
        <IndirectMaterialCheckout
          onClose={() => setShowIndirectMaterialCheckout(false)}
          onSuccess={() => {
            setShowIndirectMaterialCheckout(false)
            setRefreshKey(prev => prev + 1)
          }}
        />
      )}
    </div>
  )
}

export default Inventory
