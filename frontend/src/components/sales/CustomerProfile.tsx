import { useState, useEffect } from 'react'
import { getCustomer, getCustomerPricing, getShipToLocations, getCustomerContacts, getSalesCalls, getCustomerForecasts, getCustomerUsage, deleteShipToLocation, deleteCustomerContact, deleteSalesCall, deleteCustomerForecast, deleteCustomerPricing } from '../../api/customers'
import { getItems } from '../../api/inventory'
import { formatNumber, formatCurrency } from '../../utils/formatNumber'
import CreateShipToLocation from './CreateShipToLocation'
import CreateContact from './CreateContact'
import CreateSalesCall from './CreateSalesCall'
import CreateForecast from './CreateForecast'
import CreateCustomerPricing from './CreateCustomerPricing'
import './CustomerProfile.css'

interface Customer {
  id: number
  customer_id: string
  name: string
  contact_name?: string
  email?: string
  phone?: string
  address?: string
  city?: string
  state?: string
  zip_code?: string
  country?: string
  payment_terms?: string
  notes?: string
  is_active: boolean
}

interface CustomerProfileProps {
  customerId: number
  onClose: () => void
}

type TabType = 'overview' | 'pricing' | 'ship-to' | 'contacts' | 'sales-calls' | 'usage' | 'forecast'

function CustomerProfile({ customerId, onClose }: CustomerProfileProps) {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [loading, setLoading] = useState(true)
  const [pricing, setPricing] = useState<any[]>([])
  const [shipToLocations, setShipToLocations] = useState<any[]>([])
  const [contacts, setContacts] = useState<any[]>([])
  const [salesCalls, setSalesCalls] = useState<any[]>([])
  const [forecasts, setForecasts] = useState<any[]>([])
  const [usage, setUsage] = useState<any>(null)
  const [items, setItems] = useState<any[]>([])
  const [showShipToForm, setShowShipToForm] = useState(false)
  const [showContactForm, setShowContactForm] = useState(false)
  const [showSalesCallForm, setShowSalesCallForm] = useState(false)
  const [showForecastForm, setShowForecastForm] = useState(false)
  const [showPricingForm, setShowPricingForm] = useState(false)
  const [editingShipTo, setEditingShipTo] = useState<any>(null)
  const [editingContact, setEditingContact] = useState<any>(null)
  const [editingSalesCall, setEditingSalesCall] = useState<any>(null)
  const [editingForecast, setEditingForecast] = useState<any>(null)
  const [editingPricing, setEditingPricing] = useState<any>(null)

  useEffect(() => {
    loadCustomerData()
  }, [customerId])

  const handleDeleteShipTo = async (id: number) => {
    if (!confirm('Are you sure you want to delete this ship-to location?')) return
    try {
      await deleteShipToLocation(id)
      alert('Ship-to location deleted successfully!')
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to delete ship-to location')
    }
  }

  const handleDeleteContact = async (id: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return
    try {
      await deleteCustomerContact(id)
      alert('Contact deleted successfully!')
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to delete contact')
    }
  }

  const handleDeleteSalesCall = async (id: number) => {
    if (!confirm('Are you sure you want to delete this sales call?')) return
    try {
      await deleteSalesCall(id)
      alert('Sales call deleted successfully!')
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to delete sales call')
    }
  }

  const handleDeleteForecast = async (id: number) => {
    if (!confirm('Are you sure you want to delete this forecast?')) return
    try {
      await deleteCustomerForecast(id)
      alert('Forecast deleted successfully!')
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to delete forecast')
    }
  }

  const handleDeletePricing = async (id: number) => {
    if (!confirm('Are you sure you want to delete this pricing record?')) return
    try {
      await deleteCustomerPricing(id)
      alert('Pricing deleted successfully!')
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to delete pricing')
    }
  }

  const loadCustomerData = async () => {
    try {
      setLoading(true)
      const [customerData, pricingData, locationsData, contactsData, callsData, forecastsData, usageData, itemsData] = await Promise.all([
        getCustomer(customerId),
        getCustomerPricing(customerId),
        getShipToLocations(customerId),
        getCustomerContacts(customerId),
        getSalesCalls(customerId),
        getCustomerForecasts(customerId),
        getCustomerUsage(customerId),
        getItems()
      ])
      
      setCustomer(customerData)
      setPricing(pricingData)
      setShipToLocations(locationsData)
      setContacts(contactsData)
      setSalesCalls(callsData)
      setForecasts(forecastsData)
      setUsage(usageData)
      setItems(itemsData)
    } catch (error) {
      console.error('Failed to load customer data:', error)
      alert('Failed to load customer data')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content customer-profile-modal" onClick={(e) => e.stopPropagation()}>
          <div className="loading">Loading customer profile...</div>
        </div>
      </div>
    )
  }

  if (!customer) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content customer-profile-modal" onClick={(e) => e.stopPropagation()}>
          <div className="error">Customer not found</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content customer-profile-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{customer.name}</h2>
            <p className="customer-id">Customer ID: {customer.customer_id}</p>
          </div>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <div className="customer-profile-tabs">
          <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>
            Overview
          </button>
          <button className={activeTab === 'pricing' ? 'active' : ''} onClick={() => setActiveTab('pricing')}>
            Pricing
          </button>
          <button className={activeTab === 'ship-to' ? 'active' : ''} onClick={() => setActiveTab('ship-to')}>
            Ship-To Locations
          </button>
          <button className={activeTab === 'contacts' ? 'active' : ''} onClick={() => setActiveTab('contacts')}>
            Contacts
          </button>
          <button className={activeTab === 'sales-calls' ? 'active' : ''} onClick={() => setActiveTab('sales-calls')}>
            Sales Calls
          </button>
          <button className={activeTab === 'usage' ? 'active' : ''} onClick={() => setActiveTab('usage')}>
            Usage & Volume
          </button>
          <button className={activeTab === 'forecast' ? 'active' : ''} onClick={() => setActiveTab('forecast')}>
            Forecast
          </button>
        </div>

        <div className="customer-profile-content">
          {activeTab === 'overview' && (
            <div className="overview-tab">
              <div className="info-section">
                <h3>Contact Information</h3>
                <div className="info-grid">
                  <div><strong>Email:</strong> {customer.email || 'N/A'}</div>
                  <div><strong>Phone:</strong> {customer.phone || 'N/A'}</div>
                  <div><strong>Contact Name:</strong> {customer.contact_name || 'N/A'}</div>
                  <div><strong>Payment Terms:</strong> {customer.payment_terms || 'N/A'}</div>
                </div>
              </div>

              <div className="info-section">
                <h3>Address</h3>
                <div>
                  {customer.address && <div>{customer.address}</div>}
                  <div>{customer.city}{customer.state ? `, ${customer.state}` : ''} {customer.zip_code}</div>
                  <div>{customer.country || 'USA'}</div>
                </div>
              </div>

              {customer.notes && (
                <div className="info-section">
                  <h3>Notes</h3>
                  <p>{customer.notes}</p>
                </div>
              )}

              <div className="info-section">
                <h3>Quick Stats</h3>
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-value">{shipToLocations.length}</div>
                    <div className="stat-label">Ship-To Locations</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{contacts.length}</div>
                    <div className="stat-label">Contacts</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{salesCalls.length}</div>
                    <div className="stat-label">Sales Calls</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{pricing.length}</div>
                    <div className="stat-label">Pricing Items</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'pricing' && (
            <div className="pricing-tab">
              <div className="tab-header">
                <h3>Customer Pricing</h3>
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setEditingPricing(null)
                    setShowPricingForm(true)
                  }}
                >
                  Add Pricing
                </button>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Item SKU</th>
                    <th>Item Name</th>
                    <th>Unit Price</th>
                    <th>Unit of Measure</th>
                    <th>Effective Date</th>
                    <th>Expiry Date</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pricing.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="no-data">No pricing records found</td>
                    </tr>
                  ) : (
                    pricing.map((p) => (
                      <tr key={p.id}>
                        <td>{p.item?.sku || 'N/A'}</td>
                        <td>{p.item?.name || 'N/A'}</td>
                        <td>{formatCurrency(p.unit_price)}</td>
                        <td>{p.unit_of_measure}</td>
                        <td>{p.effective_date}</td>
                        <td>{p.expiry_date || 'N/A'}</td>
                        <td>{p.is_active ? 'Active' : 'Inactive'}</td>
                        <td>
                          <button 
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              setEditingPricing(p)
                              setShowPricingForm(true)
                            }}
                          >
                            Edit
                          </button>
                          <button 
                            className="btn btn-sm btn-danger"
                            onClick={() => handleDeletePricing(p.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'ship-to' && (
            <div className="ship-to-tab">
              <div className="tab-header">
                <h3>Ship-To Locations</h3>
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setEditingShipTo(null)
                    setShowShipToForm(true)
                  }}
                >
                  Add Location
                </button>
              </div>
              <div className="locations-grid">
                {shipToLocations.length === 0 ? (
                  <div className="no-data">No ship-to locations found</div>
                ) : (
                  shipToLocations.map((location) => (
                    <div key={location.id} className="location-card">
                      <div className="location-header">
                        <h4>{location.location_name}</h4>
                        {location.is_default && <span className="badge">Default</span>}
                      </div>
                      <div className="location-details">
                        <div>{location.address}</div>
                        <div>{location.city}{location.state ? `, ${location.state}` : ''} {location.zip_code}</div>
                        <div>{location.country || 'USA'}</div>
                        {location.contact_name && <div><strong>Contact:</strong> {location.contact_name}</div>}
                        {location.phone && <div><strong>Phone:</strong> {location.phone}</div>}
                        {location.email && <div><strong>Email:</strong> {location.email}</div>}
                      </div>
                      <div className="location-actions">
                        <button 
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            setEditingShipTo(location)
                            setShowShipToForm(true)
                          }}
                        >
                          Edit
                        </button>
                        <button 
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDeleteShipTo(location.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === 'contacts' && (
            <div className="contacts-tab">
              <div className="tab-header">
                <h3>Contacts</h3>
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setEditingContact(null)
                    setShowContactForm(true)
                  }}
                >
                  Add Contact
                </button>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Title</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Mobile</th>
                    <th>Primary</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="no-data">No contacts found</td>
                    </tr>
                  ) : (
                    contacts.map((contact) => (
                      <tr key={contact.id}>
                        <td>{contact.full_name}</td>
                        <td>{contact.title || 'N/A'}</td>
                        <td>{contact.email || 'N/A'}</td>
                        <td>{contact.phone || 'N/A'}</td>
                        <td>{contact.mobile || 'N/A'}</td>
                        <td>{contact.is_primary ? 'Yes' : 'No'}</td>
                        <td>
                          <button 
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              setEditingContact(contact)
                              setShowContactForm(true)
                            }}
                          >
                            Edit
                          </button>
                          <button 
                            className="btn btn-sm btn-danger"
                            onClick={() => handleDeleteContact(contact.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'sales-calls' && (
            <div className="sales-calls-tab">
              <div className="tab-header">
                <h3>Sales Calls</h3>
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setEditingSalesCall(null)
                    setShowSalesCallForm(true)
                  }}
                >
                  Log Call
                </button>
              </div>
              <div className="sales-calls-list">
                {salesCalls.length === 0 ? (
                  <div className="no-data">No sales calls logged</div>
                ) : (
                  salesCalls.map((call) => (
                    <div key={call.id} className="sales-call-card">
                      <div className="call-header">
                        <div>
                          <strong>{new Date(call.call_date).toLocaleString()}</strong>
                          <span className="call-type">{call.call_type}</span>
                        </div>
                        {call.contact_name && <div>Contact: {call.contact_name}</div>}
                      </div>
                      {call.subject && <div className="call-subject"><strong>Subject:</strong> {call.subject}</div>}
                      <div className="call-notes">{call.notes}</div>
                      {call.follow_up_required && (
                        <div className="follow-up">
                          <strong>Follow-up required:</strong> {call.follow_up_date ? new Date(call.follow_up_date).toLocaleDateString() : 'Date not set'}
                        </div>
                      )}
                      <div className="call-actions">
                        <button 
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            setEditingSalesCall(call)
                            setShowSalesCallForm(true)
                          }}
                        >
                          Edit
                        </button>
                        <button 
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDeleteSalesCall(call.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === 'usage' && (
            <div className="usage-tab">
              <h3>Usage & Volume</h3>
              {usage && usage.usage ? (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Item SKU</th>
                      <th>Item Name</th>
                      <th>Total Quantity</th>
                      <th>YTD Quantity</th>
                      <th>Total Orders</th>
                      <th>YTD Orders</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.usage.map((item: any) => (
                      <tr key={item.item_id}>
                        <td>{item.item_sku || 'N/A'}</td>
                        <td>{item.item_name || 'N/A'}</td>
                        <td>{item.total_quantity ? formatNumber(item.total_quantity) : '0.00'}</td>
                        <td>{item.ytd_quantity ? formatNumber(item.ytd_quantity) : '0.00'}</td>
                        <td>{item.order_count || 0}</td>
                        <td>{item.ytd_order_count || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="no-data">No usage data available</div>
              )}
            </div>
          )}

          {activeTab === 'forecast' && (
            <div className="forecast-tab">
              <div className="tab-header">
                <h3>Forecasting</h3>
                <button 
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    setEditingForecast(null)
                    setShowForecastForm(true)
                  }}
                >
                  Add Forecast
                </button>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>Item SKU</th>
                    <th>Item Name</th>
                    <th>Forecast Quantity</th>
                    <th>Unit of Measure</th>
                    <th>Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {forecasts.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="no-data">No forecasts found</td>
                    </tr>
                  ) : (
                    forecasts.map((forecast) => (
                      <tr key={forecast.id}>
                        <td>{forecast.forecast_period}</td>
                        <td>{forecast.item_sku || 'N/A'}</td>
                        <td>{forecast.item_name || 'N/A'}</td>
                        <td>{forecast.forecast_quantity ? formatNumber(forecast.forecast_quantity) : ''}</td>
                        <td>{forecast.unit_of_measure}</td>
                        <td>{forecast.notes || 'N/A'}</td>
                        <td>
                          <button 
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              setEditingForecast(forecast)
                              setShowForecastForm(true)
                            }}
                          >
                            Edit
                          </button>
                          <button 
                            className="btn btn-sm btn-danger"
                            onClick={() => handleDeleteForecast(forecast.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Forms */}
      {showShipToForm && (
        <CreateShipToLocation
          customerId={customerId}
          location={editingShipTo}
          onClose={() => {
            setShowShipToForm(false)
            setEditingShipTo(null)
          }}
          onSuccess={loadCustomerData}
        />
      )}

      {showContactForm && (
        <CreateContact
          customerId={customerId}
          contact={editingContact}
          onClose={() => {
            setShowContactForm(false)
            setEditingContact(null)
          }}
          onSuccess={loadCustomerData}
        />
      )}

      {showSalesCallForm && (
        <CreateSalesCall
          customerId={customerId}
          call={editingSalesCall}
          onClose={() => {
            setShowSalesCallForm(false)
            setEditingSalesCall(null)
          }}
          onSuccess={loadCustomerData}
        />
      )}

      {showForecastForm && (
        <CreateForecast
          customerId={customerId}
          forecast={editingForecast}
          onClose={() => {
            setShowForecastForm(false)
            setEditingForecast(null)
          }}
          onSuccess={loadCustomerData}
        />
      )}

      {showPricingForm && (
        <CreateCustomerPricing
          customerId={customerId}
          pricing={editingPricing}
          onClose={() => {
            setShowPricingForm(false)
            setEditingPricing(null)
          }}
          onSuccess={loadCustomerData}
        />
      )}
    </div>
  )
}

export default CustomerProfile
