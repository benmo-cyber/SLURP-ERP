import { useState, useEffect } from 'react'
import { getVendor, updateVendor, approveVendor, getSupplierSurvey, getSupplierDocuments, getVendorItems, createSupplierDocument, updateSupplierDocument } from '../../api/quality'
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
  payment_terms?: string
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
    street_address: vendor.street_address || '',
    city: vendor.city || '',
    state: vendor.state || '',
    zip_code: vendor.zip_code || '',
    country: vendor.country || 'USA',
    phone: vendor.phone || '',
    email: vendor.email || '',
    contact_name: vendor.contact_name || '',
    payment_terms: vendor.payment_terms || '',
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
        street_address: data.street_address || '',
        city: data.city || '',
        state: data.state || '',
        zip_code: data.zip_code || '',
        country: data.country || 'USA',
        phone: data.phone || '',
        email: data.email || '',
        contact_name: data.contact_name || '',
        payment_terms: data.payment_terms || '',
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
        street_address: formData.street_address || null,
        city: formData.city || null,
        state: formData.state || null,
        zip_code: formData.zip_code || null,
        country: formData.country || 'USA',
        phone: formData.phone || null,
        email: formData.email || null,
        contact_name: formData.contact_name || null,
        payment_terms: formData.payment_terms || null,
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
      street_address: vendor.street_address || '',
      city: vendor.city || '',
      state: vendor.state || '',
      zip_code: vendor.zip_code || '',
      country: vendor.country || 'USA',
      phone: vendor.phone || '',
      email: vendor.email || '',
      contact_name: vendor.contact_name || '',
      payment_terms: vendor.payment_terms || '',
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
                  <label>Street Address</label>
                  <input
                    type="text"
                    value={formData.street_address}
                    onChange={(e) => setFormData({ ...formData, street_address: e.target.value })}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>City</label>
                    <input
                      type="text"
                      value={formData.city}
                      onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>State</label>
                    <input
                      type="text"
                      value={formData.state}
                      onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>ZIP Code</label>
                    <input
                      type="text"
                      value={formData.zip_code}
                      onChange={(e) => setFormData({ ...formData, zip_code: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Country</label>
                    <input
                      type="text"
                      value={formData.country}
                      onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                    />
                  </div>
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
                  <label>Payment Terms</label>
                  <input
                    type="text"
                    placeholder="e.g. Net 30, Net 60, Due on Receipt"
                    value={formData.payment_terms}
                    onChange={(e) => setFormData({ ...formData, payment_terms: e.target.value })}
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
                  <span>
                    {vendor.street_address || vendor.address || ''}
                    {vendor.city && `, ${vendor.city}`}
                    {vendor.state && `, ${vendor.state}`}
                    {vendor.zip_code && ` ${vendor.zip_code}`}
                    {vendor.country && `, ${vendor.country}`}
                    {!vendor.street_address && !vendor.address && !vendor.city && 'N/A'}
                  </span>
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
                <div className="info-item">
                  <label>Payment Terms:</label>
                  <span>{vendor.payment_terms || 'N/A'}</span>
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
                  { name: 'Certificate of Insurance', type: 'certificate_of_insurance' },
                  { name: 'Letter of Guarantee', type: 'letter_of_guarantee' },
                  { name: 'Third-Party Audit Certificate', type: 'third_party_audit' },
                  { name: 'Recall Statement', type: 'recall_plan' },
                  { name: 'Completed Wildwood Ingredients Questionnaire', type: 'other' }
                ].map(doc => {
                  const docType = doc.type
                  const existingDoc = documents.find(d => d.document_type === docType)
                  const hasDoc = !!existingDoc
                  return (
                    <div key={doc.name} className="document-item">
                      <input 
                        type="checkbox" 
                        checked={hasDoc} 
                        onChange={() => {
                          if (!hasDoc) {
                            // Trigger file upload
                            const input = document.createElement('input')
                            input.type = 'file'
                            input.accept = '.pdf,.doc,.docx'
                            input.onchange = async (e: any) => {
                              const file = e.target.files[0]
                              if (file) {
                                try {
                                  setLoading(true)
                                  const formData = new FormData()
                                  formData.append('vendor', vendor.id.toString())
                                  formData.append('document_type', docType)
                                  formData.append('document_name', doc.name)
                                  formData.append('file', file)
                                  await createSupplierDocument(formData)
                                  await loadDocuments()
                                  alert('Document uploaded successfully')
                                } catch (error: any) {
                                  console.error('Failed to upload document:', error)
                                  alert(error.response?.data?.detail || error.message || 'Failed to upload document')
                                } finally {
                                  setLoading(false)
                                }
                              }
                            }
                            input.click()
                          }
                        }}
                      />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc.name}</label>
                      {hasDoc && existingDoc && (
                        <span className="document-status">
                          {existingDoc.expiration_date && new Date(existingDoc.expiration_date) < new Date() ? ' (Expired)' : ' (Current)'}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
              <div className="document-category">
                <h4>Food Safety Information</h4>
                {[
                  { name: 'FSMA Statement', type: 'fsma_statement' },
                  { name: 'HACCP Plan and flowchart', type: 'haccp_plan' },
                  { name: 'Food Defense Statement', type: 'food_defense_statement' },
                  { name: 'Environmental Sampling Monitoring Statement', type: 'other' }
                ].map(doc => {
                  const docType = doc.type
                  const existingDoc = documents.find(d => d.document_type === docType)
                  const hasDoc = !!existingDoc
                  return (
                    <div key={doc.name} className="document-item">
                      <input 
                        type="checkbox" 
                        checked={hasDoc} 
                        onChange={() => {
                          if (!hasDoc) {
                            const input = document.createElement('input')
                            input.type = 'file'
                            input.accept = '.pdf,.doc,.docx'
                            input.onchange = async (e: any) => {
                              const file = e.target.files[0]
                              if (file) {
                                try {
                                  setLoading(true)
                                  const formData = new FormData()
                                  formData.append('vendor', vendor.id.toString())
                                  formData.append('document_type', docType)
                                  formData.append('document_name', doc.name)
                                  formData.append('file', file)
                                  await createSupplierDocument(formData)
                                  await loadDocuments()
                                  alert('Document uploaded successfully')
                                } catch (error: any) {
                                  console.error('Failed to upload document:', error)
                                  alert(error.response?.data?.detail || error.message || 'Failed to upload document')
                                } finally {
                                  setLoading(false)
                                }
                              }
                            }
                            input.click()
                          }
                        }}
                      />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc.name}</label>
                      {hasDoc && existingDoc && (
                        <span className="document-status">
                          {existingDoc.expiration_date && new Date(existingDoc.expiration_date) < new Date() ? ' (Expired)' : ' (Current)'}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
              <div className="document-category">
                <h4>Per Ingredient Documents</h4>
                {[
                  { name: 'Spec Sheet', type: 'spec_sheet' },
                  { name: 'Safety Data Sheet (SDS)', type: 'sds' },
                  { name: 'Nutritional Information', type: 'nutritional_info' },
                  { name: 'Allergen Statement', type: 'allergen_statement' },
                  { name: 'Ingredient Breakdown', type: 'other' },
                  { name: 'Storage and Shelf-Life Statement', type: 'other' },
                  { name: 'Halal Certificate (if applicable)', type: 'halal_certificate' },
                  { name: 'Kosher Certificate', type: 'kosher_certificate' },
                  { name: 'BE and GMO Statement', type: 'other' },
                  { name: 'Certificate of Origin', type: 'other' },
                  { name: 'Proposition 65 Statement', type: 'other' },
                  { name: 'PHOs Statement', type: 'other' },
                  { name: 'Sterilization/Irradiation Statement', type: 'other' },
                  { name: 'No Animal Testing Statement', type: 'other' },
                  { name: 'Pesticide Statement', type: 'other' },
                  { name: 'Heavy Metal Statement', type: 'other' },
                  { name: 'Food Grade Packaging Statement', type: 'other' },
                  { name: 'PFAS Statement for Product and Packaging', type: 'other' }
                ].map(doc => {
                  const docType = doc.type
                  const existingDoc = documents.find(d => d.document_type === docType)
                  const hasDoc = !!existingDoc
                  return (
                    <div key={doc.name} className="document-item">
                      <input 
                        type="checkbox" 
                        checked={hasDoc} 
                        onChange={() => {
                          if (!hasDoc) {
                            const input = document.createElement('input')
                            input.type = 'file'
                            input.accept = '.pdf,.doc,.docx'
                            input.onchange = async (e: any) => {
                              const file = e.target.files[0]
                              if (file) {
                                try {
                                  setLoading(true)
                                  const formData = new FormData()
                                  formData.append('vendor', vendor.id.toString())
                                  formData.append('document_type', docType)
                                  formData.append('document_name', doc.name)
                                  formData.append('file', file)
                                  await createSupplierDocument(formData)
                                  await loadDocuments()
                                  alert('Document uploaded successfully')
                                } catch (error: any) {
                                  console.error('Failed to upload document:', error)
                                  alert(error.response?.data?.detail || error.message || 'Failed to upload document')
                                } finally {
                                  setLoading(false)
                                }
                              }
                            }
                            input.click()
                          }
                        }}
                      />
                      <label className={hasDoc ? 'completed' : 'missing'}>{doc.name}</label>
                      {hasDoc && existingDoc && (
                        <span className="document-status">
                          {existingDoc.expiration_date && new Date(existingDoc.expiration_date) < new Date() ? ' (Expired)' : ' (Current)'}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            {documents.length > 0 && (
              <div className="uploaded-documents">
                <h4>Uploaded Documents</h4>
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th>Document Name</th>
                      <th>Type</th>
                      <th>Uploaded</th>
                      <th>Expiration</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map(doc => (
                      <tr key={doc.id}>
                        <td>{doc.document_name}</td>
                        <td>{doc.document_type}</td>
                        <td>{new Date(doc.uploaded_at).toLocaleDateString()}</td>
                        <td>
                          {doc.expiration_date ? (
                            <span className={new Date(doc.expiration_date) < new Date() ? 'expired' : ''}>
                              {new Date(doc.expiration_date).toLocaleDateString()}
                            </span>
                          ) : 'N/A'}
                        </td>
                        <td>
                          <button
                            className="btn btn-sm btn-secondary"
                            onClick={() => {
                              // Open document in new tab
                              window.open(`http://localhost:8000/api/supplier-documents/${doc.id}/download/`, '_blank')
                            }}
                          >
                            View
                          </button>
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => {
                              // Replace document
                              const input = document.createElement('input')
                              input.type = 'file'
                              input.accept = '.pdf,.doc,.docx'
                              input.onchange = async (e: any) => {
                                const file = e.target.files[0]
                                if (file) {
                                  try {
                                    setLoading(true)
                                    const formData = new FormData()
                                    formData.append('vendor', vendor.id.toString())
                                    formData.append('document_type', doc.document_type)
                                    formData.append('document_name', doc.document_name)
                                    formData.append('file', file)
                                    // Update existing document
                                    await updateSupplierDocument(doc.id, formData)
                                    await loadDocuments()
                                    alert('Document replaced successfully')
                                  } catch (error: any) {
                                    console.error('Failed to replace document:', error)
                                    alert(error.response?.data?.detail || error.message || 'Failed to replace document')
                                  } finally {
                                    setLoading(false)
                                  }
                                }
                              }
                              input.click()
                            }}
                          >
                            Replace
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
