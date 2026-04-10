import { useState, useEffect } from 'react'
import { getCustomer, getCustomerPricing, getShipToLocations, getCustomerContacts, getSalesCalls, getCustomerForecasts, getCustomerUsage, updateCustomer, updateCustomerContact, deleteShipToLocation, deleteCustomerContact, deleteSalesCall, deleteCustomerForecast, deleteCustomerPricing } from '../../api/customers'
import { getItems } from '../../api/inventory'
import { formatNumber, formatCurrency } from '../../utils/formatNumber'
import { formatAppDate, formatAppDateTime } from '../../utils/appDateFormat'
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
  bill_to_address?: string
  bill_to_city?: string
  bill_to_state?: string
  bill_to_zip_code?: string
  bill_to_country?: string
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
  const [showEditProfile, setShowEditProfile] = useState(false)
  const [editFormData, setEditFormData] = useState({
    name: '',
    contact_name: '',
    email: '',
    phone: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'USA',
    bill_to_same_as_hq: false,
    bill_to_address: '',
    bill_to_city: '',
    bill_to_state: '',
    bill_to_zip_code: '',
    bill_to_country: '',
    payment_terms: '',
    notes: '',
    is_active: true,
  })
  const [savingProfile, setSavingProfile] = useState(false)

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

  const handleToggleContactFlag = async (contact: any, field: 'is_ap_contact' | 'is_purchasing_contact') => {
    const value = !contact[field]
    try {
      await updateCustomerContact(contact.id, {
        customer: customerId,
        first_name: contact.first_name,
        last_name: contact.last_name,
        title: contact.title ?? '',
        contact_type: contact.contact_type || 'general',
        emails: Array.isArray(contact.emails) ? contact.emails : [],
        phone: contact.phone ?? '',
        mobile: contact.mobile ?? '',
        is_primary: contact.is_primary ?? false,
        is_ap_contact: field === 'is_ap_contact' ? value : (contact.is_ap_contact ?? false),
        is_purchasing_contact: field === 'is_purchasing_contact' ? value : (contact.is_purchasing_contact ?? false),
        is_active: contact.is_active !== undefined ? contact.is_active : true,
        notes: contact.notes ?? '',
      })
      loadCustomerData()
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to update contact')
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

  const openEditProfile = () => {
    if (!customer) return
    const hq = {
      address: customer.address || '',
      city: customer.city || '',
      state: customer.state || '',
      zip_code: customer.zip_code || '',
      country: customer.country || 'USA',
    }
    const billTo = {
      bill_to_address: customer.bill_to_address ?? customer.address ?? '',
      bill_to_city: customer.bill_to_city ?? customer.city ?? '',
      bill_to_state: customer.bill_to_state ?? customer.state ?? '',
      bill_to_zip_code: customer.bill_to_zip_code ?? customer.zip_code ?? '',
      bill_to_country: customer.bill_to_country ?? customer.country ?? 'USA',
    }
    const billToSameAsHq =
      (billTo.bill_to_address || '') === (hq.address || '') &&
      (billTo.bill_to_city || '') === (hq.city || '') &&
      (billTo.bill_to_state || '') === (hq.state || '') &&
      (billTo.bill_to_zip_code || '') === (hq.zip_code || '') &&
      (billTo.bill_to_country || '') === (hq.country || '')
    setEditFormData({
      name: customer.name,
      contact_name: customer.contact_name || '',
      email: customer.email || '',
      phone: customer.phone || '',
      address: hq.address,
      city: hq.city,
      state: hq.state,
      zip_code: hq.zip_code,
      country: hq.country,
      bill_to_same_as_hq: billToSameAsHq,
      ...billTo,
      payment_terms: customer.payment_terms || '',
      notes: customer.notes || '',
      is_active: customer.is_active,
    })
    setShowEditProfile(true)
  }

  const getProfilePayload = () => {
    const billToSameAsHq = editFormData.bill_to_same_as_hq
    return {
      customer_id: customer!.customer_id,
      name: editFormData.name,
      contact_name: editFormData.contact_name || null,
      email: editFormData.email || null,
      phone: editFormData.phone || null,
      address: editFormData.address || null,
      city: editFormData.city || null,
      state: editFormData.state || null,
      zip_code: editFormData.zip_code || null,
      country: editFormData.country || null,
      bill_to_address: billToSameAsHq ? (editFormData.address || null) : (editFormData.bill_to_address || null),
      bill_to_city: billToSameAsHq ? (editFormData.city || null) : (editFormData.bill_to_city || null),
      bill_to_state: billToSameAsHq ? (editFormData.state || null) : (editFormData.bill_to_state || null),
      bill_to_zip_code: billToSameAsHq ? (editFormData.zip_code || null) : (editFormData.bill_to_zip_code || null),
      bill_to_country: billToSameAsHq ? (editFormData.country || null) : (editFormData.bill_to_country || null),
      payment_terms: editFormData.payment_terms || null,
      notes: editFormData.notes || null,
      is_active: editFormData.is_active,
    }
  }

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!customer) return
    try {
      setSavingProfile(true)
      await updateCustomer(customer.id, getProfilePayload())
      await loadCustomerData()
      setShowEditProfile(false)
    } catch (error: any) {
      alert(error.response?.data?.detail || error.message || 'Failed to update customer')
    } finally {
      setSavingProfile(false)
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
          <div className="customer-profile-header-actions">
            {!showEditProfile ? (
              <button type="button" className="btn btn-secondary btn-sm" onClick={openEditProfile}>
                Edit profile
              </button>
            ) : null}
            <button onClick={onClose} className="close-btn">×</button>
          </div>
        </div>

        {showEditProfile ? (
          <div className="customer-profile-edit">
            <h3>Edit customer profile</h3>
            <form onSubmit={handleSaveProfile} className="customer-profile-edit-form">
              <div className="form-row">
                <div className="form-group">
                  <label>Name *</label>
                  <input
                    type="text"
                    value={editFormData.name}
                    onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Contact name</label>
                  <input
                    type="text"
                    value={editFormData.contact_name}
                    onChange={(e) => setEditFormData({ ...editFormData, contact_name: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={editFormData.email}
                    onChange={(e) => setEditFormData({ ...editFormData, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="text"
                    value={editFormData.phone}
                    onChange={(e) => setEditFormData({ ...editFormData, phone: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Headquarters address — Street</label>
                <textarea
                  value={editFormData.address}
                  onChange={(e) => {
                    const next = { ...editFormData, address: e.target.value }
                    if (next.bill_to_same_as_hq) {
                      next.bill_to_address = next.address
                      next.bill_to_city = next.city
                      next.bill_to_state = next.state
                      next.bill_to_zip_code = next.zip_code
                      next.bill_to_country = next.country
                    }
                    setEditFormData(next)
                  }}
                  rows={2}
                  placeholder="Street, suite/unit, building (do not include city, state, or country—use the fields below)"
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>HQ City</label>
                  <input
                    type="text"
                    value={editFormData.city}
                    onChange={(e) => {
                      const next = { ...editFormData, city: e.target.value }
                      if (next.bill_to_same_as_hq) next.bill_to_city = next.city
                      setEditFormData(next)
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>HQ State</label>
                  <input
                    type="text"
                    value={editFormData.state}
                    onChange={(e) => {
                      const next = { ...editFormData, state: e.target.value }
                      if (next.bill_to_same_as_hq) next.bill_to_state = next.state
                      setEditFormData(next)
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>HQ ZIP code</label>
                  <input
                    type="text"
                    value={editFormData.zip_code}
                    onChange={(e) => {
                      const next = { ...editFormData, zip_code: e.target.value }
                      if (next.bill_to_same_as_hq) next.bill_to_zip_code = next.zip_code
                      setEditFormData(next)
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>HQ Country</label>
                  <input
                    type="text"
                    value={editFormData.country}
                    onChange={(e) => {
                      const next = { ...editFormData, country: e.target.value }
                      if (next.bill_to_same_as_hq) next.bill_to_country = next.country
                      setEditFormData(next)
                    }}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={editFormData.bill_to_same_as_hq}
                    onChange={(e) => {
                      const checked = e.target.checked
                      setEditFormData({
                        ...editFormData,
                        bill_to_same_as_hq: checked,
                        ...(checked
                          ? {
                              bill_to_address: editFormData.address,
                              bill_to_city: editFormData.city,
                              bill_to_state: editFormData.state,
                              bill_to_zip_code: editFormData.zip_code,
                              bill_to_country: editFormData.country,
                            }
                          : {}),
                      })
                    }}
                  />
                  Bill-to address is same as HQ
                </label>
              </div>
              {!editFormData.bill_to_same_as_hq && (
                <>
                  <div className="form-group">
                    <label>Bill-to address — Street</label>
                    <textarea
                      value={editFormData.bill_to_address}
                      onChange={(e) => setEditFormData({ ...editFormData, bill_to_address: e.target.value })}
                      rows={2}
                      placeholder="Bill-to street address"
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Bill-to City</label>
                      <input
                        type="text"
                        value={editFormData.bill_to_city}
                        onChange={(e) => setEditFormData({ ...editFormData, bill_to_city: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Bill-to State</label>
                      <input
                        type="text"
                        value={editFormData.bill_to_state}
                        onChange={(e) => setEditFormData({ ...editFormData, bill_to_state: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Bill-to ZIP code</label>
                      <input
                        type="text"
                        value={editFormData.bill_to_zip_code}
                        onChange={(e) => setEditFormData({ ...editFormData, bill_to_zip_code: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Bill-to Country</label>
                      <input
                        type="text"
                        value={editFormData.bill_to_country}
                        onChange={(e) => setEditFormData({ ...editFormData, bill_to_country: e.target.value })}
                      />
                    </div>
                  </div>
                </>
              )}

              <div className="form-group">
                <label>Payment terms</label>
                <input
                  type="text"
                  value={editFormData.payment_terms}
                  onChange={(e) => setEditFormData({ ...editFormData, payment_terms: e.target.value })}
                  placeholder="e.g., Net 30, Net 15, Due on Receipt"
                />
              </div>
              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={editFormData.notes}
                  onChange={(e) => setEditFormData({ ...editFormData, notes: e.target.value })}
                  rows={3}
                />
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={editFormData.is_active}
                    onChange={(e) => setEditFormData({ ...editFormData, is_active: e.target.checked })}
                  />
                  Active
                </label>
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditProfile(false)} disabled={savingProfile}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={savingProfile}>
                  {savingProfile ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        ) : (
          <>
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
                <h3>Headquarters address</h3>
                <div className="address-display">
                  {customer.address && <div className="address-street">{customer.address}</div>}
                  {(customer.city || customer.state || customer.zip_code || customer.country) && (
                    <div className="address-city-state">
                      {[customer.city, customer.state, customer.zip_code].filter(Boolean).join(', ')}
                      {customer.country ? ` — ${customer.country}` : ''}
                    </div>
                  )}
                  {!customer.address && !customer.city && !customer.state && !customer.zip_code && !customer.country && (
                    <div className="text-muted">No address on file</div>
                  )}
                </div>
              </div>

              <div className="info-section">
                <h3>Bill-to address</h3>
                <div className="address-display">
                  {(() => {
                    const hqStr = [customer.address, customer.city, customer.state, customer.zip_code, customer.country].filter(Boolean).join(' ')
                    const billStr = [customer.bill_to_address, customer.bill_to_city, customer.bill_to_state, customer.bill_to_zip_code, customer.bill_to_country].filter(Boolean).join(' ')
                    const sameAsHq = billStr ? hqStr.trim() === billStr.trim() : !billStr
                    if (sameAsHq) return <div className="text-muted">Same as headquarters</div>
                    return (
                      <>
                        {customer.bill_to_address && <div className="address-street">{customer.bill_to_address}</div>}
                        {(customer.bill_to_city || customer.bill_to_state || customer.bill_to_zip_code || customer.bill_to_country) && (
                          <div className="address-city-state">
                            {[customer.bill_to_city, customer.bill_to_state, customer.bill_to_zip_code].filter(Boolean).join(', ')}
                            {customer.bill_to_country ? ` — ${customer.bill_to_country}` : ''}
                          </div>
                        )}
                      </>
                    )
                  })()}
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
                    <th>Incoterms</th>
                    <th>Effective Date</th>
                    <th>Expiry Date</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pricing.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="no-data">No pricing records found</td>
                    </tr>
                  ) : (
                    pricing.map((p) => (
                      <tr key={p.id}>
                        <td>{p.item?.sku || 'N/A'}</td>
                        <td>{p.item?.name || 'N/A'}</td>
                        <td>{formatCurrency(p.unit_price)}</td>
                        <td>{p.unit_of_measure}</td>
                        <td>{[p.incoterms, p.incoterms_place].filter(Boolean).join(' ') || '—'}</td>
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
                    <th>Type</th>
                    <th>Title</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Mobile</th>
                    <th>Primary</th>
                    <th>A/P contact</th>
                    <th>Purchasing contact</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="no-data">No contacts found</td>
                    </tr>
                  ) : (
                    contacts.map((contact) => (
                      <tr key={contact.id}>
                        <td>{contact.full_name}</td>
                        <td>{contact.contact_type ? String(contact.contact_type).charAt(0).toUpperCase() + String(contact.contact_type).slice(1) : 'General'}</td>
                        <td>{contact.title || 'N/A'}</td>
                        <td>{(contact.emails && contact.emails.length > 0) ? contact.emails.join(', ') : 'N/A'}</td>
                        <td>{contact.phone || 'N/A'}</td>
                        <td>{contact.mobile || 'N/A'}</td>
                        <td>{contact.is_primary ? 'Yes' : 'No'}</td>
                        <td>
                          <input
                            type="checkbox"
                            checked={!!contact.is_ap_contact}
                            onChange={() => handleToggleContactFlag(contact, 'is_ap_contact')}
                            title="Receives invoices when issued"
                          />
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={!!contact.is_purchasing_contact}
                            onChange={() => handleToggleContactFlag(contact, 'is_purchasing_contact')}
                            title="Receives sales order confirmations when issued"
                          />
                        </td>
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
                          <strong>{formatAppDateTime(call.call_date)}</strong>
                          <span className="call-type">{call.call_type}</span>
                        </div>
                        {call.contact_name && <div>Contact: {call.contact_name}</div>}
                      </div>
                      {call.subject && <div className="call-subject"><strong>Subject:</strong> {call.subject}</div>}
                      <div className="call-notes">{call.notes}</div>
                      {call.follow_up_required && (
                        <div className="follow-up">
                          <strong>Follow-up required:</strong> {call.follow_up_date ? formatAppDate(call.follow_up_date) : 'Date not set'}
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
          </>
        )}
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
