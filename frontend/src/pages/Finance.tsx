import { useState } from 'react'
import GeneralLedger from '../components/finance/GeneralLedger'
import Invoices from '../components/finance/Invoices'
import JournalEntries from '../components/finance/JournalEntries'
import PricingManagement from '../components/finance/PricingManagement'
import FinancialReports from '../components/finance/FinancialReports'
import CostMasterList from '../components/finance/CostMasterList'
import AccountsPayable from '../components/finance/AccountsPayable'
import AccountsReceivable from '../components/finance/AccountsReceivable'
import './Finance.css'

function Finance() {
  const [activeTab, setActiveTab] = useState<'ledger' | 'invoices' | 'journal' | 'pricing' | 'reports' | 'cost-master' | 'ap' | 'ar'>('ledger')

  return (
    <div className="finance-page">
      <div className="page-header">
        <h1>Finance</h1>
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
          className={`tab-button ${activeTab === 'cost-master' ? 'active' : ''}`}
          onClick={() => setActiveTab('cost-master')}
        >
          Cost Master List
        </button>
        <button
          className={`tab-button ${activeTab === 'ap' ? 'active' : ''}`}
          onClick={() => setActiveTab('ap')}
        >
          Accounts Payable
        </button>
        <button
          className={`tab-button ${activeTab === 'ar' ? 'active' : ''}`}
          onClick={() => setActiveTab('ar')}
        >
          Accounts Receivable
        </button>
      </div>

      <div className="finance-content">
        {activeTab === 'ledger' && <GeneralLedger />}
        {activeTab === 'invoices' && <Invoices />}
        {activeTab === 'journal' && <JournalEntries />}
        {activeTab === 'pricing' && <PricingManagement />}
        {activeTab === 'reports' && <FinancialReports />}
        {activeTab === 'cost-master' && <CostMasterList />}
        {activeTab === 'ap' && <AccountsPayable />}
        {activeTab === 'ar' && <AccountsReceivable />}
      </div>
    </div>
  )
}

export default Finance
