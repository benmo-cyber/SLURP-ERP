import { useState, useEffect } from 'react'
import { getVendor, updateVendor, approveVendor, getSupplierSurvey, getSupplierDocuments, getVendorItems } from '../../api/quality'
import './VendorDetail.css'

interface Vendor {
  id: number
  name: string
  vendor_id?: string
  approval_status: string
  risk_profile: string
  on_time_performance: number
  quality_complaints: number
  approved_date?: string
  address?: string
  phone?: string
  email?: string
  contact_name?: string
  notes?: string
}

interface VendorDetailProps {
  vendor: Vendor
  onClose: () => void
}

function VendorDetail({ vendor: initialVendor, onClose }: VendorDetailProps) {
  const [vendor, setVendor] = useState<Vendor>(initialVendor)
  const [activeTab, setActiveTab] = useState<'overview' | 'survey' | 'documents' | 'exceptions' | 'history' | 'items'>('overview')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [survey, setSurvey] = useState<any>(null)
  const [documents, setDocuments] = useState<any[]>([])
  const [vendorItems, setVendorItems] = useState<any[]>([])
  const [formData, setFormData] = useState({
    name: vendor.name,
    vendor_id: vendor.vendor_id || '',
    address: vendor.address || '',
    phone: vendor.phone || '',
    email: vendor.email || '',
    contact_name: vendor.contact_name || '',
    notes: vendor.notes || '',
  })

  useEffect(() => {
    loadVendorDetails()
    loadSurvey()
    loadDocuments()
    loadVendorItems()
  }, [initialVendor.id])

  const loadVendorDetails = async () => {
    try {
      setLoading(true)
      const data = await getVendor(initialVendor.id)
      setVendor(data)
      setFormData({
        name: data.name || '',
        vendor_id: data.vendor_id || '',
        address: data.address || '',
        phone: data.phone || '',
        email: data.email || '',
        contact_name: data.contact_name || '',
        notes: data.notes || '',
      })
    } catch (error) {
      console.error('Failed to load vendor details:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    try {
      setLoading(true)
      const updateData = {
        ...formData,
        // Convert empty strings to null for optional fields
        vendor_id: formData.vendor_id || null,
        address: formData.address || null,
        phone: formData.phone || null,
        email: formData.email || null,
        contact_name: formData.contact_name || null,
        notes: formData.notes || null,
      }
      await updateVendor(vendor.id, updateData)
      await loadVendorDetails()
      setEditing(false)
      alert('Vendor information updated successfully')
    } catch (error: any) {
      console.error('Failed to update vendor:', error)
      const errorMessage = error.response?.data?.detail || error.response?.data?.message || error.message || 'Failed to save changes'
      alert(`Error: ${errorMessage}`)
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => {
    setFormData({
      name: vendor.name || '',
      vendor_id: vendor.vendor_id || '',
      address: vendor.address || '',
      phone: vendor.phone || '',
      email: vendor.email || '',
      contact_name: vendor.contact_name || '',
      notes: vendor.notes || '',
    })
    setEditing(false)
  }

  const loadSurvey = async () => {
    try {
      const data = await getSupplierSurvey(initialVendor.id)
      setSurvey(data)
    } catch (error) {
      console.error('Failed to load survey:', error)
    }
  }

  const loadDocuments = async () => {
    try {
      const data = await getSupplierDocuments(initialVendor.id)
      setDocuments(data)
    } catch (error) {
      console.error('Failed to load documents:', error)
    }
  }

  const loadVendorItems = async () => {
    try {
      const data = await getVendorItems(initialVendor.id)
      setVendorItems(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load vendor items:', error)
      setVendorItems([])
    }
  }

  const handleApproveVendor = async () => {
    if (!confirm(`Are you sure you want to approve ${vendor.name}?`)) {
      return
    }

    try {
      setLoading(true)
      await approveVendor(vendor.id)
      await loadVendorDetails()
      alert('Vendor approved successfully!')
    } catch (error: any) {
      console.error('Failed to approve vendor:', error)
      alert(error.response?.data?.detail || 'Failed to approve vendor')
    } finally {
      setLoading(false)
    }
  }

  if (loading && !editing) {
    return <div className="loading">Loading vendor details...</div>
  }

  return (
    <div className="vendor-detail">
      <div className="vendor-detail-header">
        <h2>{vendor.name}</h2>
        <button onClick={onClose} className="btn btn-secondary">← Back to Vendors</button>
      </div>

      <div className="vendor-detail-tabs">
        <button
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab-button ${activeTab === 'survey' ? 'active' : ''}`}
          onClick={() => setActiveTab('survey')}
        >
          Survey
        </button>
        <button
          className={`tab-button ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Documents
        </button>
        <button
          className={`tab-button ${activeTab === 'items' ? 'active' : ''}`}
          onClick={() => setActiveTab('items')}
        >
          Items
        </button>
        <button
          className={`tab-button ${activeTab === 'exceptions' ? 'active' : ''}`}
          onClick={() => setActiveTab('exceptions')}
        >
          Exceptions
        </button>
        <button
          className={`tab-button ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          History
        </button>
      </div>

      <div className="vendor-detail-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="overview-header">
              <h3>Vendor Information</h3>
              <div className="overview-actions">
                {vendor.approval_status !== 'approved' && (
                  <button 
                    onClick={handleApproveVendor} 
                    className="btn btn-primary"
                    disabled={loading}
                  >
                    Approve Vendor
                  </button>
                )}
                {!editing && (
                  <button onClick={() => setEditing(true)} className="btn btn-secondary">
                    Edit
                  </button>
                )}
              </div>
            </div>

            {editing ? (
              <div className="vendor-edit-form">
                <div className="form-group">
                  <label>Vendor Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Vendor ID</label>
                  <input
                    type="text"
                    value={formData.vendor_id}
                    onChange={(e) => setFormData({ ...formData, vendor_id: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Address</label>
                  <input
                    type="text"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="text"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Contact Name</label>
                  <input
                    type="text"
                    value={formData.contact_name}
                    onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Notes</label>
                  <textarea
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                    rows={4}
                  />
                </div>
                <div className="form-actions">
                  <button onClick={handleSave} className="btn btn-primary" disabled={loading}>
                    Save
                  </button>
                  <button onClick={handleCancel} className="btn btn-secondary" disabled={loading}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="vendor-info">
                <div className="info-item">
                  <label>Vendor ID:</label>
                  <span>{vendor.vendor_id || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Approval Status:</label>
                  <span className={`status-badge ${vendor.approval_status}`}>{vendor.approval_status}</span>
                </div>
                <div className="info-item">
                  <label>Risk Profile:</label>
                  <span className={`risk-${vendor.risk_profile}`}>
                    {vendor.risk_profile === '1' ? '1 - Low Risk' : 
                     vendor.risk_profile === '2' ? '2 - Medium Risk' : 
                     vendor.risk_profile === '3' ? '3 - High Risk' : vendor.risk_profile}
                  </span>
                </div>
                <div className="info-item">
                  <label>On-Time Performance:</label>
                  <span>{vendor.on_time_performance.toFixed(1)}%</span>
                </div>
                <div className="info-item">
                  <label>Quality Complaints:</label>
                  <span>{vendor.quality_complaints}</span>
                </div>
                <div className="info-item">
                  <label>Address:</label>
                  <span>{vendor.address || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Phone:</label>
                  <span>{vendor.phone || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Email:</label>
                  <span>{vendor.email || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <label>Contact Name:</label>
                  <span>{vendor.contact_name || 'N/A'}</span>
                </div>
                {vendor.notes && (
                  <div className="info-item">
                    <label>Notes:</label>
                    <span>{vendor.notes}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'survey' && (
          <div className="survey-tab">
            {survey ? (
              <div className="survey-content">
                <h3>Supplier Quality Survey</h3>
                <div className="survey-status">
                  <strong>Status:</strong> <span className={`status-badge ${survey.status}`}>{survey.status}</span>
                </div>
                {survey.status === 'approved' && survey.approved_date && (
                  <div className="survey-info">
                    <p><strong>Approved by:</strong> {survey.approved_by || 'DOOF'}</p>
                    <p><strong>Approved date:</strong> {new Date(survey.approved_date).toLocaleDateString()}</p>
                  </div>
                )}
                {survey.company_info && Object.keys(survey.company_info).length > 0 && (
                  <div className="survey-section">
                    <h4>Company Information</h4>
                    <pre>{JSON.stringify(survey.company_info, null, 2)}</pre>
                  </div>
                )}
                {survey.compliance_responses && Object.keys(survey.compliance_responses).length > 0 && (
                  <div className="survey-section">
                    <h4>Compliance Responses</h4>
                    <pre>{JSON.stringify(survey.compliance_responses, null, 2)}</pre>
                  </div>
                )}
                {survey.quality_program_responses && Object.keys(survey.quality_program_responses).length > 0 && (
                  <div className="survey-section">
                    <h4>Quality Program Responses</h4>
                    <pre>{JSON.stringify(survey.quality_program_responses, null, 2)}</pre>
                  </div>
                )}
              </div>
            ) : (
              <div className="survey-empty">
                <p>No survey has been submitted for this vendor yet.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="documents-tab">
            <h3>Required Documents</h3>
            <div className="documents-checklist">
              <div className="document-category">
                <h4>General Documents</h4>
                {[
                  'Certificate of Insurance',
                  'Letter of Guarantee',
                  'Third-Party Audit Certificate',
                  'Recall Statement',
                  'Completed Wildwood Ingredients Questionnaire'
                ].map(doc => {
                  const hasDoc = documents.some(d => d.document_name === doc || d.document_type === doc.toLowerCase().replace(/\s+/g, '_'))
                  return (
                    <div key={doc} className="document-item">
                      <input type="checkbox" checked={hasDoc} disabled />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc}</label>
                    </div>
                  )
                })}
              </div>
              <div className="document-category">
                <h4>Food Safety Information</h4>
                {[
                  'FSMA Statement',
                  'HACCP Plan and flowchart',
                  'Food Defense Statement',
                  'Environmental Sampling Monitoring Statement'
                ].map(doc => {
                  const hasDoc = documents.some(d => d.document_name === doc || d.document_type === doc.toLowerCase().replace(/\s+/g, '_'))
                  return (
                    <div key={doc} className="document-item">
                      <input type="checkbox" checked={hasDoc} disabled />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc}</label>
                    </div>
                  )
                })}
              </div>
              <div className="document-category">
                <h4>Per Ingredient Documents</h4>
                {[
                  'Spec Sheet',
                  'Safety Data Sheet (SDS)',
                  'Nutritional Information',
                  'Allergen Statement',
                  'Ingredient Breakdown',
                  'Storage and Shelf-Life Statement',
                  'Halal Certificate (if applicable)',
                  'Kosher Certificate',
                  'BE and GMO Statement',
                  'Certificate of Origin',
                  'Proposition 65 Statement',
                  'PHOs Statement',
                  'Sterilization/Irradiation Statement',
                  'No Animal Testing Statement',
                  'Pesticide Statement',
                  'Heavy Metal Statement',
                  'Food Grade Packaging Statement',
                  'PFAS Statement for Product and Packaging'
                ].map(doc => {
                  const hasDoc = documents.some(d => d.document_name === doc || d.document_type === doc.toLowerCase().replace(/\s+/g, '_'))
                  return (
                    <div key={doc} className="document-item">
                      <input type="checkbox" checked={hasDoc} disabled />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc}</label>
                    </div>
                  )
                })}
              </div>
            </div>
            {documents.length > 0 && (
              <div className="uploaded-documents">
                <h4>Uploaded Documents</h4>
                <ul>
                  {documents.map(doc => (
                    <li key={doc.id}>
                      {doc.document_name} ({doc.document_type})
                      {doc.expiration_date && (
                        <span className={new Date(doc.expiration_date) < new Date() ? 'expired' : ''}>
                          {' '}- Expires: {new Date(doc.expiration_date).toLocaleDateString()}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {activeTab === 'items' && (
          <div className="items-tab">
            <h3>Approved Items</h3>
            {vendorItems.length > 0 ? (
              <table className="vendor-items-table">
                <thead>
                  <tr>
                    <th>WWI Product Code</th>
                    <th>Item Name</th>
                    <th>Unit of Measure</th>
                    <th>Pack Size</th>
                    <th>Price</th>
                    <th>YTD Usage</th>
                  </tr>
                </thead>
                <tbody>
                  {vendorItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.sku}</td>
                      <td>{item.name}</td>
                      <td>{item.unit_of_measure}</td>
                      <td>{item.pack_size ? `${item.pack_size} ${item.unit_of_measure}` : 'N/A'}</td>
                      <td>{item.price ? `$${item.price.toFixed(2)}/${item.unit_of_measure}` : 'N/A'}</td>
                      <td>{item.ytd_usage.toFixed(2)} {item.unit_of_measure}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="items-empty">
                <p>No approved items found for this vendor.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'exceptions' && (
          <div className="exceptions-tab">
            <p>Temporary exceptions will be displayed here.</p>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="history-tab">
            <p>Vendor history will be displayed here.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default VendorDetail
