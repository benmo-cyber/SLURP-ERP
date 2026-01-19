import { useState } from 'react'
import FinancialDashboard from '../components/finance/FinancialDashboard'
import GeneralLedger from '../components/finance/GeneralLedger'
import Invoices from '../components/finance/Invoices'
import JournalEntries from '../components/finance/JournalEntries'
import PricingManagement from '../components/finance/PricingManagement'
import FinancialReports from '../components/finance/FinancialReports'
import CostMasterList from '../components/finance/CostMasterList'
import AccountsPayable from '../components/finance/AccountsPayable'
import AccountsReceivable from '../components/finance/AccountsReceivable'
import PLActual from '../components/finance/PLActual'
import PLProForma from '../components/finance/PLProForma'
import './Finance.css'

function Finance() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'ledger' | 'invoices' | 'journal' | 'pricing' | 'reports' | 'cost-master' | 'ap' | 'ar' | 'pl-actual' | 'pl-proforma'>('dashboard')

  return (
    <div className="finance-page">
      <div className="page-header">
        <h1>Finance</h1>
      </div>

      <div className="finance-tabs">
        <button
          className={`tab-button ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
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
        <button
          className={`tab-button ${activeTab === 'pl-actual' ? 'active' : ''}`}
          onClick={() => setActiveTab('pl-actual')}
        >
          P&L Actual
        </button>
        <button
          className={`tab-button ${activeTab === 'pl-proforma' ? 'active' : ''}`}
          onClick={() => setActiveTab('pl-proforma')}
        >
          P&L Pro-Forma
        </button>
      </div>

      <div className="finance-content">
        {activeTab === 'dashboard' && <FinancialDashboard />}
        {activeTab === 'ledger' && <GeneralLedger />}
        {activeTab === 'invoices' && <Invoices />}
        {activeTab === 'journal' && <JournalEntries />}
        {activeTab === 'pricing' && <PricingManagement />}
        {activeTab === 'reports' && <FinancialReports />}
        {activeTab === 'cost-master' && <CostMasterList />}
        {activeTab === 'ap' && <AccountsPayable />}
        {activeTab === 'ar' && <AccountsReceivable />}
        {activeTab === 'pl-actual' && <PLActual />}
        {activeTab === 'pl-proforma' && <PLProForma />}
      </div>
    </div>
  )
}

export default Finance
