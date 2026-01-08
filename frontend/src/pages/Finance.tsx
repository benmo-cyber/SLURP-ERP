import { useState } from 'react'
import GeneralLedger from '../components/finance/GeneralLedger'
import Invoices from '../components/finance/Invoices'
import JournalEntries from '../components/finance/JournalEntries'
import PricingManagement from '../components/finance/PricingManagement'
import FinancialReports from '../components/finance/FinancialReports'
import CreatePurchaseOrder from '../components/finance/CreatePurchaseOrder'
import PurchaseOrderList from '../components/finance/PurchaseOrderList'
import CostMasterList from '../components/finance/CostMasterList'
import './Finance.css'

function Finance() {
  const [activeTab, setActiveTab] = useState<'ledger' | 'invoices' | 'journal' | 'pricing' | 'reports' | 'purchase-orders' | 'cost-master'>('ledger')
  const [showCreatePO, setShowCreatePO] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCreatePOSuccess = () => {
    setShowCreatePO(false)
    setRefreshKey(prev => prev + 1)
  }

  return (
    <div className="finance-page">
      <div className="page-header">
        <h1>Finance</h1>
        {activeTab === 'purchase-orders' && (
          <button onClick={() => setShowCreatePO(true)} className="btn btn-primary">
            Create Purchase Order
          </button>
        )}
      </div>

      <div className="finance-tabs">
        <button
          className={`tab-button ${activeTab === 'ledger' ? 'active' : ''}`}
          onClick={() => setActiveTab('ledger')}
        >
          General Ledger
        </button>
        <button
          className={`tab-button ${activeTab === 'invoices' ? 'active' : ''}`}
          onClick={() => setActiveTab('invoices')}
        >
          Invoices
        </button>
        <button
          className={`tab-button ${activeTab === 'journal' ? 'active' : ''}`}
          onClick={() => setActiveTab('journal')}
        >
          Journal Entries
        </button>
        <button
          className={`tab-button ${activeTab === 'pricing' ? 'active' : ''}`}
          onClick={() => setActiveTab('pricing')}
        >
          Pricing Management
        </button>
        <button
          className={`tab-button ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          Financial Reports
        </button>
        <button
          className={`tab-button ${activeTab === 'purchase-orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('purchase-orders')}
        >
          Purchase Orders
        </button>
        <button
          className={`tab-button ${activeTab === 'cost-master' ? 'active' : ''}`}
          onClick={() => setActiveTab('cost-master')}
        >
          Cost Master List
        </button>
      </div>

      <div className="finance-content">
        {activeTab === 'ledger' && <GeneralLedger />}
        {activeTab === 'invoices' && <Invoices />}
        {activeTab === 'journal' && <JournalEntries />}
        {activeTab === 'pricing' && <PricingManagement />}
        {activeTab === 'reports' && <FinancialReports />}
        {activeTab === 'purchase-orders' && <PurchaseOrderList key={refreshKey} />}
        {activeTab === 'cost-master' && <CostMasterList />}
      </div>

      {showCreatePO && (
        <CreatePurchaseOrder
          onClose={() => setShowCreatePO(false)}
          onSuccess={handleCreatePOSuccess}
        />
      )}
    </div>
  )
}

export default Finance
