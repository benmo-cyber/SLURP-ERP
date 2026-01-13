import { useState } from 'react'
import VendorApproval from '../components/quality/VendorApproval'
import LotTracking from '../components/quality/LotTracking'
import FinishedGoodsList from '../components/quality/FinishedGoodsList'
import './Quality.css'

function Quality() {
  const [activeTab, setActiveTab] = useState<'vendors' | 'lot-tracking' | 'finished-goods'>('vendors')

  return (
    <div className="quality-page">
      <div className="page-header">
        <h1>Quality</h1>
      </div>

      <div className="quality-tabs">
        <button
          className={`tab-button ${activeTab === 'vendors' ? 'active' : ''}`}
          onClick={() => setActiveTab('vendors')}
        >
          Vendor Approval
        </button>
        <button
          className={`tab-button ${activeTab === 'lot-tracking' ? 'active' : ''}`}
          onClick={() => setActiveTab('lot-tracking')}
        >
          Lot Tracking
        </button>
        <button
          className={`tab-button ${activeTab === 'finished-goods' ? 'active' : ''}`}
          onClick={() => setActiveTab('finished-goods')}
        >
          Finished Goods
        </button>
      </div>

      <div className="quality-content">
        {activeTab === 'vendors' && <VendorApproval />}
        {activeTab === 'lot-tracking' && <LotTracking />}
        {activeTab === 'finished-goods' && <FinishedGoodsList />}
      </div>
    </div>
  )
}

export default Quality
