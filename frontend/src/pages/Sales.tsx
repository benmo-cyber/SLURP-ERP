import { useState } from 'react'
import CreateSalesOrder from '../components/sales/CreateSalesOrder'
import CustomerManagement from '../components/sales/CustomerManagement'
import CheckOutModal from '../components/sales/CheckOutModal'
import SalesOrdersList from '../components/sales/SalesOrdersList'
import Calendar from '../components/calendar/Calendar'
import CRMDashboard from '../components/sales/CRMDashboard'
import './Sales.css'

export type SalesTabId = 'crm' | 'orders' | 'calendar'

const NAV_SECTIONS: { label: string; items: { id: SalesTabId; label: string }[] }[] = [
  { label: 'Overview', items: [{ id: 'crm', label: 'CRM' }] },
  { label: 'Orders', items: [{ id: 'orders', label: 'Sales Orders' }] },
  { label: 'Planning', items: [{ id: 'calendar', label: 'Calendar' }] },
]

function Sales() {
  const [activeTab, setActiveTab] = useState<SalesTabId>('crm')
  const [showCreateSO, setShowCreateSO] = useState(false)
  const [editingSalesOrder, setEditingSalesOrder] = useState<any>(null)
  const [showCustomerManagement, setShowCustomerManagement] = useState(false)
  const [showCheckOut, setShowCheckOut] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCreateSOSuccess = () => {
    setShowCreateSO(false)
    setEditingSalesOrder(null)
    setRefreshKey(prev => prev + 1)
  }

  const handleEditSalesOrder = (order: any) => {
    setEditingSalesOrder(order)
    setShowCreateSO(true)
  }

  const handleCheckOutSuccess = () => {
    setShowCheckOut(false)
    setRefreshKey(prev => prev + 1)
  }

  return (
    <div className="sales-page">
      <header className="sales-header">
        <h1>Sales</h1>
        {activeTab === 'orders' && (
          <div className="sales-header-actions">
            <button onClick={() => setShowCustomerManagement(true)} className="btn btn-secondary">
              Manage Customers
            </button>
            <button onClick={() => setShowCheckOut(true)} className="btn btn-primary">
              Check Out
            </button>
            <button onClick={() => setShowCreateSO(true)} className="btn btn-primary">
              Create Sales Order from Customer PO
            </button>
          </div>
        )}
      </header>

      <div className="sales-layout">
        <nav className="sales-sidebar">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="sales-nav-section">
              <div className="sales-nav-section-label">{section.label}</div>
              <ul className="sales-nav-list">
                {section.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`sales-nav-item ${activeTab === item.id ? 'active' : ''}`}
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

        <main className="sales-main">
          {activeTab === 'crm' && <CRMDashboard />}
          {activeTab === 'calendar' && <Calendar />}
          {activeTab === 'orders' && (
            <SalesOrdersList
              refreshKey={refreshKey}
              onEditOrder={handleEditSalesOrder}
            />
          )}
        </main>
      </div>

      {showCreateSO && (
        <CreateSalesOrder
          onClose={() => {
            setShowCreateSO(false)
            setEditingSalesOrder(null)
          }}
          onSuccess={handleCreateSOSuccess}
          salesOrder={editingSalesOrder}
        />
      )}
      {showCustomerManagement && (
        <CustomerManagement
          onClose={() => setShowCustomerManagement(false)}
        />
      )}
      {showCheckOut && (
        <CheckOutModal
          onClose={() => setShowCheckOut(false)}
          onSuccess={handleCheckOutSuccess}
        />
      )}
    </div>
  )
}

export default Sales
