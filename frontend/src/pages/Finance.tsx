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
import BankReconciliation from '../components/finance/BankReconciliation'
import FiscalPeriods from '../components/finance/FiscalPeriods'
import KPIs from '../components/finance/KPIs'
import MarginTrends from '../components/finance/MarginTrends'
import RawMaterialLotCosts from '../components/finance/RawMaterialLotCosts'
import './Finance.css'

export type FinanceTabId =
  | 'dashboard'
  | 'kpis'
  | 'ledger'
  | 'journal'
  | 'invoices'
  | 'ar'
  | 'ap'
  | 'bank-recon'
  | 'periods'
  | 'pricing'
  | 'cost-master'
  | 'margin-trends'
  | 'reports'
  | 'pl-actual'
  | 'pl-proforma'

const NAV_SECTIONS: { label: string; items: { id: FinanceTabId; label: string }[] }[] = [
  { label: 'Overview', items: [{ id: 'dashboard', label: 'Dashboard' }, { id: 'kpis', label: 'KPIs' }] },
  {
    label: 'Accounting',
    items: [
      { id: 'ledger', label: 'General Ledger' },
      { id: 'journal', label: 'Journal Entries' },
      { id: 'periods', label: 'Fiscal Periods' },
      { id: 'bank-recon', label: 'Bank Reconciliation' },
    ],
  },
  {
    label: 'Invoicing',
    items: [
      { id: 'invoices', label: 'Invoices' },
      { id: 'ar', label: 'Accounts Receivable' },
    ],
  },
  {
    label: 'Payables',
    items: [{ id: 'ap', label: 'Accounts Payable' }],
  },
  {
    label: 'Pricing & cost',
    items: [
      { id: 'pricing', label: 'Pricing Management' },
      { id: 'cost-master', label: 'Cost Master List' },
      { id: 'margin-trends', label: 'Price & margin trends' },
      { id: 'rm-lot-costs', label: 'RM lot cost vs estimate' },
    ],
  },
  {
    label: 'Reports',
    items: [
      { id: 'reports', label: 'Financial Reports' },
      { id: 'pl-actual', label: 'P&L Actual' },
      { id: 'pl-proforma', label: 'P&L Pro-Forma' },
    ],
  },
]

function Finance() {
  const [activeTab, setActiveTab] = useState<FinanceTabId>('dashboard')

  return (
    <div className="finance-page">
      <header className="finance-header">
        <h1>Finance</h1>
      </header>

      <div className="finance-layout">
        <nav className="finance-sidebar">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="finance-nav-section">
              <div className="finance-nav-section-label">{section.label}</div>
              <ul className="finance-nav-list">
                {section.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`finance-nav-item ${activeTab === item.id ? 'active' : ''}`}
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

        <main className="finance-main">
          {activeTab === 'dashboard' && <FinancialDashboard />}
          {activeTab === 'kpis' && <KPIs />}
          {activeTab === 'ledger' && <GeneralLedger />}
          {activeTab === 'invoices' && <Invoices onNavigateToTab={setActiveTab} />}
          {activeTab === 'journal' && <JournalEntries />}
          {activeTab === 'pricing' && <PricingManagement />}
          {activeTab === 'reports' && <FinancialReports onNavigateToTab={setActiveTab} />}
          {activeTab === 'cost-master' && <CostMasterList />}
          {activeTab === 'margin-trends' && <MarginTrends />}
          {activeTab === 'rm-lot-costs' && <RawMaterialLotCosts />}
          {activeTab === 'ap' && <AccountsPayable />}
          {activeTab === 'ar' && <AccountsReceivable onNavigateToTab={setActiveTab} />}
          {activeTab === 'bank-recon' && <BankReconciliation />}
          {activeTab === 'periods' && <FiscalPeriods />}
          {activeTab === 'pl-actual' && <PLActual />}
          {activeTab === 'pl-proforma' && <PLProForma />}
        </main>
      </div>
    </div>
  )
}

export default Finance
