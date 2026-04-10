import { useState } from 'react'
import VendorApproval from '../components/quality/VendorApproval'
import LotTracking from '../components/quality/LotTracking'
import FinishedGoodsList from '../components/quality/FinishedGoodsList'
import RDFormulasList from '../components/quality/RDFormulasList'
import CriticalControlPoints from '../components/quality/CriticalControlPoints'
import CoaLibrary from '../components/quality/CoaLibrary'
import './Quality.css'

const NAV_SECTIONS = [
  { label: 'Vendors', items: [{ id: 'vendors' as const, label: 'Vendor Approval' }] },
  {
    label: 'Tracking',
    items: [
      { id: 'lot-tracking' as const, label: 'Lot Tracking' },
      { id: 'coa-library' as const, label: 'COA library' },
    ],
  },
  { label: 'Products', items: [{ id: 'finished-goods' as const, label: 'Finished Goods' }, { id: 'rd-formulas' as const, label: 'R&D Formulas' }, { id: 'ccps' as const, label: 'Critical Control Points' }] },
]

function Quality() {
  const [activeTab, setActiveTab] = useState<
    'vendors' | 'lot-tracking' | 'coa-library' | 'finished-goods' | 'rd-formulas' | 'ccps'
  >('vendors')

  return (
    <div className="quality-page">
      <header className="quality-header">
        <h1>Quality</h1>
      </header>
      <div className="quality-layout">
        <aside className="quality-sidebar">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="quality-nav-section">
              <div className="quality-nav-section-label">{section.label}</div>
              <ul className="quality-nav-list">
                {section.items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`quality-nav-item ${activeTab === item.id ? 'active' : ''}`}
                      onClick={() => setActiveTab(item.id)}
                    >
                      {item.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>
        <main className="quality-main">
          {activeTab === 'vendors' && <VendorApproval />}
          {activeTab === 'lot-tracking' && <LotTracking />}
          {activeTab === 'coa-library' && <CoaLibrary />}
          {activeTab === 'finished-goods' && <FinishedGoodsList />}
          {activeTab === 'rd-formulas' && <RDFormulasList />}
          {activeTab === 'ccps' && <CriticalControlPoints />}
        </main>
      </div>
    </div>
  )
}

export default Quality
