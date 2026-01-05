import { useState } from 'react'
import { Link, Routes, Route, useLocation } from 'react-router-dom'
import InventorySummary from '../components/inventory/InventorySummary'
import CheckIn from '../components/inventory/CheckIn'
import './Inventory.css'

function Inventory() {
  const location = useLocation()
  const currentTab = location.pathname.split('/').pop() || 'summary'

  const tabs = [
    { id: 'summary', label: 'Inventory Summary', path: '/inventory/summary' },
    { id: 'checkin', label: 'Check In', path: '/inventory/checkin' },
  ]

  return (
    <div className="inventory-page">
      <div className="inventory-header">
        <h1>Inventory Management</h1>
      </div>
      
      <div className="inventory-tabs">
        {tabs.map((tab) => (
          <Link
            key={tab.id}
            to={tab.path}
            className={`inventory-tab ${currentTab === tab.id ? 'active' : ''}`}
          >
            {tab.label}
          </Link>
        ))}
      </div>

      <div className="inventory-content">
        <Routes>
          <Route path="summary" element={<InventorySummary />} />
          <Route path="checkin" element={<CheckIn />} />
          <Route index element={<InventorySummary />} />
        </Routes>
      </div>
    </div>
  )
}

export default Inventory

