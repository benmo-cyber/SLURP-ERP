import { useState } from 'react'
import CreateSalesOrder from '../components/sales/CreateSalesOrder'
import CustomerManagement from '../components/sales/CustomerManagement'
import CheckOutModal from '../components/sales/CheckOutModal'
import Calendar from '../components/calendar/Calendar'
import CRMDashboard from '../components/sales/CRMDashboard'
import './Sales.css'

function Sales() {
  const [activeTab, setActiveTab] = useState<'orders' | 'calendar' | 'crm'>('crm')
  const [showCreateSO, setShowCreateSO] = useState(false)
  const [showCustomerManagement, setShowCustomerManagement] = useState(false)
  const [showCheckOut, setShowCheckOut] = useState(false)

  const handleCreateSOSuccess = () => {
    setShowCreateSO(false)
  }

  return (
    <div className="sales-page">
      <div className="page-header">
        <h1>Sales</h1>
        <div className="header-actions">
          {activeTab === 'orders' && (
            <>
              <button onClick={() => setShowCustomerManagement(true)} className="btn btn-secondary">
                Manage Customers
              </button>
              <button onClick={() => setShowCheckOut(true)} className="btn btn-primary">
                Check Out
              </button>
              <button onClick={() => setShowCreateSO(true)} className="btn btn-primary">
                Create Sales Order from Customer PO
              </button>
            </>
          )}
        </div>
      </div>

      <div className="sales-tabs">
        <button
          className={`tab-button ${activeTab === 'crm' ? 'active' : ''}`}
          onClick={() => setActiveTab('crm')}
        >
          CRM
        </button>
        <button
          className={`tab-button ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('orders')}
        >
          Sales Orders
        </button>
        <button
          className={`tab-button ${activeTab === 'calendar' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar')}
        >
          Calendar
        </button>
      </div>

      <div className="page-content">
        {activeTab === 'crm' && <CRMDashboard />}
        {activeTab === 'calendar' && <Calendar />}
        {activeTab === 'orders' && (
          <div>
            {/* Sales orders content will go here */}
          </div>
        )}
      </div>

      {/* Modals - shown regardless of active tab */}
      {showCreateSO && (
        <CreateSalesOrder
          onClose={() => setShowCreateSO(false)}
          onSuccess={handleCreateSOSuccess}
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
          onSuccess={() => {
            setShowCheckOut(false)
          }}
        />
      )}
    </div>
  )
}

export default Sales
