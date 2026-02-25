import { useState } from 'react'
import VendorApproval from '../components/quality/VendorApproval'
import LotTracking from '../components/quality/LotTracking'
import FinishedGoodsList from '../components/quality/FinishedGoodsList'
import './Quality.css'

const NAV_SECTIONS = [
  { label: 'Vendors', items: [{ id: 'vendors' as const, label: 'Vendor Approval' }] },
  { label: 'Tracking', items: [{ id: 'lot-tracking' as const, label: 'Lot Tracking' }] },
  { label: 'Products', items: [{ id: 'finished-goods' as const, label: 'Finished Goods' }] },
]

function Quality() {
  const [activeTab, setActiveTab] = useState<'vendors' | 'lot-tracking' | 'finished-goods'>('vendors')

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
          {activeTab === 'finished-goods' && <FinishedGoodsList />}
        </main>
      </div>
    </div>
  )
}

export default Quality
