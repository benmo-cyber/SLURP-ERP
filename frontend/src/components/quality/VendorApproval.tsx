import { useState, useEffect } from 'react'
import { getVendors, createVendor, updateVendor, addVendorHistory } from '../../api/quality'
import CreateVendor from './CreateVendor'
import VendorDetail from './VendorDetail'
import './VendorApproval.css'

interface Vendor {
  id: number
  name: string
  vendor_id?: string
  approval_status: string
  risk_profile: string
  on_time_performance: number
  quality_complaints: number
  approved_date?: string
}

function VendorApproval() {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    loadVendors()
  }, [refreshKey])

  const loadVendors = async () => {
    try {
      setLoading(true)
      const data = await getVendors()
      setVendors(data)
    } catch (error) {
      console.error('Failed to load vendors:', error)
      alert('Failed to load vendors')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSuccess = () => {
    setShowCreate(false)
    setRefreshKey(prev => prev + 1)
  }

  const handleVendorSelect = (vendor: Vendor) => {
    setSelectedVendor(vendor)
  }

  const handleCloseDetail = () => {
    setSelectedVendor(null)
    setRefreshKey(prev => prev + 1)
  }

  const approvedVendors = vendors.filter(v => v.approval_status === 'approved')
  const pendingVendors = vendors.filter(v => v.approval_status === 'pending')
  const otherVendors = vendors.filter(v => !['approved', 'pending'].includes(v.approval_status))

  if (loading) {
    return <div className="loading">Loading vendors...</div>
  }

  return (
    <div className="vendor-approval">
      <div className="approval-header">
        <h2>Vendor Approval & Management</h2>
        <button onClick={() => setShowCreate(true)} className="btn btn-primary">
          + Add New Vendor
        </button>
      </div>

      {selectedVendor ? (
        <VendorDetail
          vendor={selectedVendor}
          onClose={handleCloseDetail}
        />
      ) : (
        <div className="vendors-container">
          <div className="vendor-section">
            <h3>Approved Vendors</h3>
            {approvedVendors.length === 0 ? (
              <div className="empty-state">No approved vendors</div>
            ) : (
              <div className="vendors-grid">
                {approvedVendors.map((vendor) => (
                  <div
                    key={vendor.id}
                    className="vendor-card approved"
                    onClick={() => handleVendorSelect(vendor)}
                  >
                    <div className="vendor-card-header">
                      <h4>{vendor.name}</h4>
                      <span className="status-badge approved">Approved</span>
                    </div>
                    <div className="vendor-metrics">
                      <div className="metric">
                        <label>On-Time Performance:</label>
                        <span className={vendor.on_time_performance >= 95 ? 'good' : vendor.on_time_performance >= 80 ? 'medium' : 'poor'}>
                          {vendor.on_time_performance.toFixed(1)}%
                        </span>
                      </div>
                      <div className="metric">
                        <label>Quality Complaints:</label>
                        <span className={vendor.quality_complaints === 0 ? 'good' : vendor.quality_complaints <= 2 ? 'medium' : 'poor'}>
                          {vendor.quality_complaints}
                        </span>
                      </div>
                      <div className="metric">
                        <label>Risk Profile:</label>
                        <span className={`risk-${vendor.risk_profile}`}>
                          {vendor.risk_profile}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="vendor-section">
            <h3>Pending Approval</h3>
            {pendingVendors.length === 0 ? (
              <div className="empty-state">No pending vendors</div>
            ) : (
              <div className="vendors-grid">
                {pendingVendors.map((vendor) => (
                  <div
                    key={vendor.id}
                    className="vendor-card pending"
                    onClick={() => handleVendorSelect(vendor)}
                  >
                    <div className="vendor-card-header">
                      <h4>{vendor.name}</h4>
                      <span className="status-badge pending">Pending</span>
                    </div>
                    <div className="vendor-metrics">
                      <div className="metric">
                        <label>Risk Profile:</label>
                        <span className={`risk-${vendor.risk_profile}`}>
                          {vendor.risk_profile}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {otherVendors.length > 0 && (
            <div className="vendor-section">
              <h3>Other Status</h3>
              <div className="vendors-grid">
                {otherVendors.map((vendor) => (
                  <div
                    key={vendor.id}
                    className="vendor-card"
                    onClick={() => handleVendorSelect(vendor)}
                  >
                    <div className="vendor-card-header">
                      <h4>{vendor.name}</h4>
                      <span className={`status-badge ${vendor.approval_status}`}>
                        {vendor.approval_status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <CreateVendor
          onClose={() => setShowCreate(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  )
}

export default VendorApproval






