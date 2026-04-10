import { useState, useEffect } from 'react'
import { getVendors } from '../../api/quality'
import { formatVendorAddress, formatVendorAddressWithSurveyFallback } from '../../utils/formatVendorAddress'
import { formatAppDateMedium } from '../../utils/appDateFormat'
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
  street_address?: string
  address?: string
  city?: string
  state?: string
  zip_code?: string
  country?: string
  survey?: { company_info?: Record<string, unknown> } | null
  /** From API — built from vendor + survey JSON */
  display_address?: string | null
  notes?: string | null
}

type FilterStatus = 'all' | 'approved' | 'pending' | 'other'

function VendorApproval() {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [filter, setFilter] = useState<FilterStatus>('all')

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

  const handleCloseDetail = () => {
    setSelectedVendor(null)
    setRefreshKey(prev => prev + 1)
  }

  const filteredVendors = vendors.filter((v) => {
    if (filter === 'all') return true
    if (filter === 'approved') return v.approval_status === 'approved'
    if (filter === 'pending') return v.approval_status === 'pending'
    return !['approved', 'pending'].includes(v.approval_status)
  })

  const formatDate = (d: string | undefined) => (d ? formatAppDateMedium(d) : '—')

  if (loading) {
    return <div className="vendor-approval-loading">Loading vendors...</div>
  }

  return (
    <div className="vendor-approval">
      <header className="vendor-approval-header">
        <h1>Vendor Approval & Management</h1>
        <button type="button" onClick={() => setShowCreate(true)} className="btn btn-primary">
          + Add New Vendor
        </button>
      </header>

      {selectedVendor ? (
        <VendorDetail vendor={selectedVendor} onClose={handleCloseDetail} />
      ) : (
        <>
          <div className="vendor-approval-filters">
            <button
              type="button"
              className={filter === 'all' ? 'active' : ''}
              onClick={() => setFilter('all')}
            >
              All ({vendors.length})
            </button>
            <button
              type="button"
              className={filter === 'approved' ? 'active' : ''}
              onClick={() => setFilter('approved')}
            >
              Approved ({vendors.filter((v) => v.approval_status === 'approved').length})
            </button>
            <button
              type="button"
              className={filter === 'pending' ? 'active' : ''}
              onClick={() => setFilter('pending')}
            >
              Pending ({vendors.filter((v) => v.approval_status === 'pending').length})
            </button>
            <button
              type="button"
              className={filter === 'other' ? 'active' : ''}
              onClick={() => setFilter('other')}
            >
              Other ({vendors.filter((v) => !['approved', 'pending'].includes(v.approval_status)).length})
            </button>
          </div>

          <div className="vendor-approval-table-wrap">
            <table className="vendor-approval-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Address</th>
                  <th>Status</th>
                  <th>Risk</th>
                  <th>On-time %</th>
                  <th>Quality complaints</th>
                  <th>Approved date</th>
                </tr>
              </thead>
              <tbody>
                {filteredVendors.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="vendor-approval-empty">
                      {filter === 'all' ? 'No vendors yet. Add one to get started.' : `No ${filter} vendors.`}
                    </td>
                  </tr>
                ) : (
                  filteredVendors.map((vendor) => (
                    <tr
                      key={vendor.id}
                      className="vendor-approval-row"
                      onClick={() => setSelectedVendor(vendor)}
                    >
                      <td>
                        <span className="vendor-name">{vendor.name}</span>
                        {vendor.vendor_id && (
                          <span className="vendor-id">{vendor.vendor_id}</span>
                        )}
                      </td>
                      <td
                        className="vendor-address-cell"
                        title={
                          formatVendorAddressWithSurveyFallback(vendor).trim() ||
                          formatVendorAddress(vendor).trim() ||
                          undefined
                        }
                      >
                        {formatVendorAddressWithSurveyFallback(vendor).trim() ||
                          formatVendorAddress(vendor).trim() ||
                          '—'}
                      </td>
                      <td>
                        <span className={`status-badge ${vendor.approval_status}`}>
                          {vendor.approval_status}
                        </span>
                      </td>
                      <td>
                        <span className={`risk risk-${vendor.risk_profile}`}>
                          {vendor.risk_profile}
                        </span>
                      </td>
                      <td>
                        <span
                          className={
                            vendor.on_time_performance >= 95
                              ? 'metric-good'
                              : vendor.on_time_performance >= 80
                                ? 'metric-medium'
                                : 'metric-poor'
                          }
                        >
                          {vendor.on_time_performance != null ? `${Number(vendor.on_time_performance).toFixed(1)}%` : '—'}
                        </span>
                      </td>
                      <td>
                        <span
                          className={
                            vendor.quality_complaints === 0
                              ? 'metric-good'
                              : vendor.quality_complaints <= 2
                                ? 'metric-medium'
                                : 'metric-poor'
                          }
                        >
                          {vendor.quality_complaints != null ? vendor.quality_complaints : '—'}
                        </span>
                      </td>
                      <td>{formatDate(vendor.approved_date)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {showCreate && (
        <CreateVendor onClose={() => setShowCreate(false)} onSuccess={handleCreateSuccess} />
      )}
    </div>
  )
}

export default VendorApproval
