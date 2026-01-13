import { useState, useEffect } from 'react'
import { getCustomers } from '../../api/customers'
import CustomerProfile from './CustomerProfile'
import CustomerManagement from './CustomerManagement'
import './CRMDashboard.css'

interface Customer {
  id: number
  customer_id: string
  name: string
  email?: string
  phone?: string
  city?: string
  state?: string
  is_active: boolean
  ship_to_locations_count?: number
  contacts_count?: number
  sales_calls_count?: number
}

function CRMDashboard() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCustomer, setSelectedCustomer] = useState<number | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [filterActive, setFilterActive] = useState<boolean | null>(null)
  const [showCustomerManagement, setShowCustomerManagement] = useState(false)

  useEffect(() => {
    loadCustomers()
  }, [])

  const loadCustomers = async () => {
    try {
      setLoading(true)
      const data = await getCustomers(filterActive !== null ? filterActive : undefined)
      setCustomers(data)
    } catch (error) {
      console.error('Failed to load customers:', error)
      alert('Failed to load customers')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCustomers()
  }, [filterActive])

  const filteredCustomers = customers.filter(customer => {
    const searchLower = searchTerm.toLowerCase()
    return (
      customer.name.toLowerCase().includes(searchLower) ||
      customer.customer_id.toLowerCase().includes(searchLower) ||
      (customer.email && customer.email.toLowerCase().includes(searchLower)) ||
      (customer.city && customer.city.toLowerCase().includes(searchLower))
    )
  })

  if (loading) {
    return <div className="loading">Loading customers...</div>
  }

  return (
    <div className="crm-dashboard">
      <div className="crm-header">
        <div className="crm-title-section">
          <h2>Customer Relationship Management</h2>
          <button 
            className="btn btn-primary"
            onClick={() => setShowCustomerManagement(true)}
          >
            + Add Customer
          </button>
        </div>
        <div className="crm-filters">
          <input
            type="text"
            placeholder="Search customers..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-input"
          />
          <div className="filter-buttons">
            <button
              className={filterActive === null ? 'active' : ''}
              onClick={() => setFilterActive(null)}
            >
              All
            </button>
            <button
              className={filterActive === true ? 'active' : ''}
              onClick={() => setFilterActive(true)}
            >
              Active
            </button>
            <button
              className={filterActive === false ? 'active' : ''}
              onClick={() => setFilterActive(false)}
            >
              Inactive
            </button>
          </div>
        </div>
      </div>

      <div className="customers-grid">
        {filteredCustomers.length === 0 ? (
          <div className="no-customers">
            {searchTerm ? 'No customers match your search' : 'No customers found'}
          </div>
        ) : (
          filteredCustomers.map((customer) => (
            <div
              key={customer.id}
              className={`customer-card ${!customer.is_active ? 'inactive' : ''}`}
              onClick={() => setSelectedCustomer(customer.id)}
            >
              <div className="customer-card-header">
                <h3>{customer.name}</h3>
                <span className="customer-id-badge">ID: {customer.customer_id}</span>
              </div>
              <div className="customer-card-body">
                {customer.email && (
                  <div className="customer-info">
                    <strong>Email:</strong> {customer.email}
                  </div>
                )}
                {customer.phone && (
                  <div className="customer-info">
                    <strong>Phone:</strong> {customer.phone}
                  </div>
                )}
                {customer.city && (
                  <div className="customer-info">
                    <strong>Location:</strong> {customer.city}{customer.state ? `, ${customer.state}` : ''}
                  </div>
                )}
              </div>
              <div className="customer-card-footer">
                <div className="customer-stats">
                  <div className="stat">
                    <span className="stat-value">{customer.ship_to_locations_count || 0}</span>
                    <span className="stat-label">Locations</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{customer.contacts_count || 0}</span>
                    <span className="stat-label">Contacts</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{customer.sales_calls_count || 0}</span>
                    <span className="stat-label">Calls</span>
                  </div>
                </div>
                <div className="customer-status">
                  {customer.is_active ? (
                    <span className="status-badge active">Active</span>
                  ) : (
                    <span className="status-badge inactive">Inactive</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {selectedCustomer && (
        <CustomerProfile
          customerId={selectedCustomer}
          onClose={() => setSelectedCustomer(null)}
        />
      )}

      {showCustomerManagement && (
        <CustomerManagement
          onClose={() => {
            setShowCustomerManagement(false)
            loadCustomers()
          }}
        />
      )}
    </div>
  )
}

export default CRMDashboard
