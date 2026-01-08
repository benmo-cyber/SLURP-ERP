import { useState } from 'react'
import VendorApproval from '../components/quality/VendorApproval'
import LotTracking from '../components/quality/LotTracking'
import CreateFinishedGood from '../components/quality/CreateFinishedGood'
import './Quality.css'

function Quality() {
  const [activeTab, setActiveTab] = useState<'vendors' | 'lot-tracking' | 'finished-goods'>('vendors')

  const handleFinishedGoodSuccess = () => {
    // Revert back to vendors tab after successful creation
    setActiveTab('vendors')
  }

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
          Create Finished Good
        </button>
      </div>

      <div className="quality-content">
        {activeTab === 'vendors' && <VendorApproval />}
        {activeTab === 'lot-tracking' && <LotTracking />}
        {activeTab === 'finished-goods' && <CreateFinishedGood onClose={() => setActiveTab('vendors')} onSuccess={handleFinishedGoodSuccess} />}
      </div>
    </div>
  )
}

export default Quality
