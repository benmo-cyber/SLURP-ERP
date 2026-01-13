import { useState, useEffect } from 'react'
import { getVendorPricing, getCustomerPricing, getItems } from '../../api/finance'
import CreateVendorPricing from './CreateVendorPricing'
import PricingHistory from './PricingHistory'
import './PricingManagement.css'

function PricingManagement() {
  const [activeTab, setActiveTab] = useState<'vendor' | 'customer' | 'history'>('vendor')
  const [vendorPricing, setVendorPricing] = useState<any[]>([])
  const [customerPricing, setCustomerPricing] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showVendorForm, setShowVendorForm] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    loadPricing()
  }, [refreshKey])

  const loadPricing = async () => {
    try {
      setLoading(true)
      const [vendorData, customerData] = await Promise.all([
        getVendorPricing(),
        getCustomerPricing()
      ])
      setVendorPricing(vendorData)
      setCustomerPricing(customerData)
    } catch (error) {
      console.error('Failed to load pricing:', error)
      alert('Failed to load pricing data')
    } finally {
      setLoading(false)
    }
  }

  const handleVendorSuccess = () => {
    setShowVendorForm(false)
    setRefreshKey(prev => prev + 1)
  }


  if (loading) {
    return <div className="loading">Loading pricing data...</div>
  }

  return (
    <div className="pricing-management">
      <div className="pricing-header">
        <h2>Pricing Management</h2>
        <div className="pricing-tabs">
          <button
            className={`pricing-tab ${activeTab === 'vendor' ? 'active' : ''}`}
            onClick={() => setActiveTab('vendor')}
          >
            Vendor Pricing
          </button>
          <button
            className={`pricing-tab ${activeTab === 'customer' ? 'active' : ''}`}
            onClick={() => setActiveTab('customer')}
          >
            Customer Pricing
          </button>
          <button
            className={`pricing-tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            Pricing History
          </button>
        </div>
      </div>

      <div className="pricing-content">
        {activeTab === 'vendor' && (
          <div className="vendor-pricing">
            <div className="section-header">
              <h3>Vendor Pricing</h3>
              <button onClick={() => setShowVendorForm(true)} className="btn btn-primary">
                + Add Vendor Pricing
              </button>
            </div>

            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Vendor</th>
                  <th>Unit Price</th>
                  <th>Unit</th>
                  <th>Effective Date</th>
                  <th>Expiry Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {vendorPricing.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      No vendor pricing found. Click "Add Vendor Pricing" to add pricing.
                    </td>
                  </tr>
                ) : (
                  vendorPricing.map((pricing) => (
                    <tr key={pricing.id}>
                      <td>{pricing.item?.name || '-'}</td>
                      <td>{pricing.vendor_name}</td>
                      <td className="amount">${pricing.unit_price.toFixed(2)}</td>
                      <td>{pricing.unit_of_measure}</td>
                      <td>{new Date(pricing.effective_date).toLocaleDateString()}</td>
                      <td>{pricing.expiry_date ? new Date(pricing.expiry_date).toLocaleDateString() : '-'}</td>
                      <td>
                        <span className={`status-badge ${pricing.is_active ? 'active' : 'inactive'}`}>
                          {pricing.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'customer' && (
          <div className="customer-pricing">
            <div className="section-header">
              <h3>Customer Pricing</h3>
              <div className="info-message">
                <small>Customer pricing is managed from the CRM tab in Sales. Go to Sales → CRM → Select Customer → Pricing tab.</small>
              </div>
            </div>

            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Customer</th>
                  <th>Unit Price</th>
                  <th>Unit</th>
                  <th>Effective Date</th>
                  <th>Expiry Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {customerPricing.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      No customer pricing found. Manage customer pricing from the CRM tab in Sales.
                    </td>
                  </tr>
                ) : (
                  customerPricing.map((pricing) => (
                    <tr key={pricing.id}>
                      <td>{pricing.item?.name || '-'}</td>
                      <td>{pricing.customer_name}</td>
                      <td className="amount">${pricing.unit_price.toFixed(2)}</td>
                      <td>{pricing.unit_of_measure}</td>
                      <td>{new Date(pricing.effective_date).toLocaleDateString()}</td>
                      <td>{pricing.expiry_date ? new Date(pricing.expiry_date).toLocaleDateString() : '-'}</td>
                      <td>
                        <span className={`status-badge ${pricing.is_active ? 'active' : 'inactive'}`}>
                          {pricing.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'history' && (
          <PricingHistory />
        )}
      </div>

      {showVendorForm && (
        <CreateVendorPricing
          onClose={() => setShowVendorForm(false)}
          onSuccess={handleVendorSuccess}
        />
      )}

    </div>
  )
}

export default PricingManagement






