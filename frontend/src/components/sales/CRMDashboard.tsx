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
    return <div className="crm-loading">Loading customers...</div>
  }

  return (
    <div className="crm-dashboard">
      <header className="crm-header">
        <div className="crm-header-inner">
          <h1>Customer Relationship Management</h1>
          <button
            type="button"
            className="btn btn-primary crm-add-btn"
            onClick={() => setShowCustomerManagement(true)}
          >
            + Add Customer
          </button>
        </div>
        <div className="crm-toolbar">
          <input
            type="text"
            placeholder="Search customers..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="crm-search"
          />
          <div className="crm-filter-pills">
            <button
              type="button"
              className={filterActive === null ? 'active' : ''}
              onClick={() => setFilterActive(null)}
            >
              All
            </button>
            <button
              type="button"
              className={filterActive === true ? 'active' : ''}
              onClick={() => setFilterActive(true)}
            >
              Active
            </button>
            <button
              type="button"
              className={filterActive === false ? 'active' : ''}
              onClick={() => setFilterActive(false)}
            >
              Inactive
            </button>
          </div>
        </div>
      </header>

      <div className="crm-table-wrap">
        <table className="crm-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Location</th>
              <th>Locations</th>
              <th>Contacts</th>
              <th>Calls</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.length === 0 ? (
              <tr>
                <td colSpan={8} className="crm-empty">
                  {searchTerm ? 'No customers match your search' : 'No customers found'}
                </td>
              </tr>
            ) : (
              filteredCustomers.map((customer) => (
                <tr
                  key={customer.id}
                  className={`crm-row ${!customer.is_active ? 'inactive' : ''}`}
                  onClick={() => setSelectedCustomer(customer.id)}
                >
                  <td>
                    <span className="crm-customer-name">{customer.name}</span>
                    <span className="crm-customer-id">{customer.customer_id}</span>
                  </td>
                  <td>{customer.email || '—'}</td>
                  <td>{customer.phone || '—'}</td>
                  <td>
                    {customer.city || customer.state
                      ? [customer.city, customer.state].filter(Boolean).join(', ')
                      : '—'}
                  </td>
                  <td>{customer.ship_to_locations_count ?? 0}</td>
                  <td>{customer.contacts_count ?? 0}</td>
                  <td>{customer.sales_calls_count ?? 0}</td>
                  <td>
                    <span className={`crm-status-badge ${customer.is_active ? 'active' : 'inactive'}`}>
                      {customer.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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
