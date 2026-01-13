import { useState, useEffect } from 'react'
import {
  getPurchaseOrders,
  getPurchaseOrder,
  updatePurchaseOrder,
  issuePurchaseOrder,
  revisePurchaseOrder,
  cancelPurchaseOrder,
  deletePurchaseOrder,
  updateDeliveryFromTracking
} from '../../api/purchaseOrders'
import './PurchaseOrderList.css'

interface PurchaseOrderItem {
  id: number
  item: {
    id: number
    name: string
  }
  description: string
  unit_cost: number
  quantity_ordered: number
  quantity_received: number
  notes: string
}

interface PurchaseOrder {
  id: number
  po_number: string
  revision_number?: number
  original_po?: number
  vendor_id: number
  vendor_name?: string
  required_date?: string
  expected_delivery_date?: string
  order_date: string
  status: string
  total?: number
  subtotal?: number
  tracking_number?: string
  carrier?: string
  items: PurchaseOrderItem[]
  shipping_terms?: string
  shipping_method?: string
  ship_to_name?: string
  ship_to_address?: string
  ship_to_city?: string
  ship_to_state?: string
  ship_to_zip?: string
  ship_to_country?: string
  vendor_address?: string
  vendor_city?: string
  vendor_state?: string
  vendor_zip?: string
  vendor_country?: string
  notes?: string
}

function PurchaseOrderList() {
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [selectedPO, setSelectedPO] = useState<PurchaseOrder | null>(null)
  const [editingRequiredDate, setEditingRequiredDate] = useState(false)
  const [requiredDateValue, setRequiredDateValue] = useState<string>('')
  const [trackingNumber, setTrackingNumber] = useState<string>('')
  const [carrier, setCarrier] = useState<string>('')
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')

  useEffect(() => {
    loadPOs()
  }, [filter])

  useEffect(() => {
    if (selectedPO) {
      setTrackingNumber(selectedPO.tracking_number || '')
      setCarrier(selectedPO.carrier || '')
      setRequiredDateValue(selectedPO.required_date || '')
    }
  }, [selectedPO])

  const loadPOs = async () => {
    try {
      setLoading(true)
      const data = await getPurchaseOrders(filter !== 'all' ? { status: filter } : undefined)
      
      // Filter to show only the latest revision of each PO number
      const poMap = new Map<string, PurchaseOrder>()
      
      data.forEach((po: PurchaseOrder) => {
        const existing = poMap.get(po.po_number)
        if (!existing || (po.revision_number || 0) > (existing.revision_number || 0)) {
          poMap.set(po.po_number, po)
        }
      })
      
      // Convert map values to array and sort
      const filteredPos = Array.from(poMap.values()).sort((a, b) => {
        return new Date(b.order_date).getTime() - new Date(a.order_date).getTime()
      })
      
      setPos(filteredPos)
    } catch (error) {
      console.error('Failed to load purchase orders:', error)
      alert('Failed to load purchase orders')
    } finally {
      setLoading(false)
    }
  }

  const handleView = async (id: number) => {
    try {
      const po = await getPurchaseOrder(id)
      setSelectedPO(po)
    } catch (error) {
      console.error('Failed to load purchase order:', error)
      alert('Failed to load purchase order details')
    }
  }

  const handleIssue = async (id: number) => {
    if (!confirm('Are you sure you want to issue this purchase order? This will update inventory.')) {
      return
    }
    try {
      await issuePurchaseOrder(id)
      alert('Purchase order issued successfully')
      loadPOs()
      if (selectedPO?.id === id) {
        setSelectedPO(null)
      }
    } catch (error: any) {
      console.error('Failed to issue purchase order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to issue purchase order')
    }
  }


  const handleRevise = async (id: number) => {
    if (!confirm('Create a revision of this purchase order? The original will be superseded.')) {
      return
    }
    try {
      await revisePurchaseOrder(id)
      alert('Purchase order revision created. Please review and issue the new revision.')
      loadPOs()
      if (selectedPO?.id === id) {
        setSelectedPO(null)
      }
    } catch (error: any) {
      console.error('Failed to revise purchase order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to revise purchase order')
    }
  }

  const handleCancel = async (id: number) => {
    if (!confirm('Are you sure you want to cancel this purchase order? This will reverse inventory changes if the PO was issued.')) {
      return
    }
    try {
      await cancelPurchaseOrder(id)
      alert('Purchase order cancelled')
      loadPOs()
      if (selectedPO?.id === id) {
        setSelectedPO(null)
      }
    } catch (error: any) {
      console.error('Failed to cancel purchase order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to cancel purchase order')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this purchase order? This action cannot be undone.')) {
      return
    }
    try {
      await deletePurchaseOrder(id)
      alert('Purchase order deleted')
      loadPOs()
      if (selectedPO?.id === id) {
        setSelectedPO(null)
      }
    } catch (error: any) {
      console.error('Failed to delete purchase order:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to delete purchase order')
    }
  }

  const handleSaveTracking = async () => {
    if (!selectedPO) return
    
    try {
      if (trackingNumber && carrier) {
        await updateDeliveryFromTracking(selectedPO.id, trackingNumber, carrier)
        await updatePurchaseOrder(selectedPO.id, {
          tracking_number: trackingNumber,
          carrier: carrier
        })
      } else {
        await updatePurchaseOrder(selectedPO.id, {
          tracking_number: trackingNumber || null,
          carrier: carrier || null
        })
      }
      
      alert('Tracking information updated')
      await loadPOs()
      if (selectedPO) {
        const updated = await getPurchaseOrder(selectedPO.id)
        setSelectedPO(updated)
      }
    } catch (error: any) {
      console.error('Failed to update tracking:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update tracking information')
    }
  }

  const handleEditRequiredDate = () => {
    setEditingRequiredDate(true)
    setRequiredDateValue(selectedPO?.required_date || '')
  }

  const handleSaveRequiredDate = async () => {
    if (!selectedPO) return
    
    try {
      await updatePurchaseOrder(selectedPO.id, {
        required_date: requiredDateValue || null
      })
      setEditingRequiredDate(false)
      alert('Required date updated')
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: any) {
      console.error('Failed to update required date:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update required date')
    }
  }

  const handleCancelEditRequiredDate = () => {
    setEditingRequiredDate(false)
    setRequiredDateValue(selectedPO?.required_date || '')
  }

  const isLate = (expectedDate?: string, requiredDate?: string) => {
    if (!expectedDate || !requiredDate) return false
    return new Date(expectedDate) > new Date(requiredDate)
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A'
    return new Date(dateString).toLocaleDateString()
  }

  const getStatusBadgeClass = (status: string) => {
    const statusMap: { [key: string]: string } = {
      draft: 'status-draft',
      issued: 'status-issued',
      received: 'status-received',
      completed: 'status-completed',
      cancelled: 'status-cancelled',
      superseded: 'status-superseded'
    }
    return statusMap[status] || 'status-default'
  }

  if (loading && pos.length === 0) {
    return <div className="loading">Loading purchase orders...</div>
  }

  if (selectedPO) {
    return (
      <div className="po-detail-view">
        <div className="po-detail-header">
          <h2>Purchase Order Details</h2>
          <button onClick={() => setSelectedPO(null)} className="btn btn-secondary">← Back to List</button>
        </div>

        <div className="po-detail-content">
          <div className="po-info-section">
            <h3>PO Information</h3>
            <div className="info-grid">
              <div className="info-item">
                <label>PO Number:</label>
                <span>
                  {selectedPO.po_number}
                  {selectedPO.revision_number && selectedPO.revision_number > 0 && (
                    <span className="revision-badge">Rev {selectedPO.revision_number}</span>
                  )}
                </span>
              </div>
              <div className="info-item">
                <label>Status:</label>
                <span className={getStatusBadgeClass(selectedPO.status)}>{selectedPO.status}</span>
              </div>
              <div className="info-item">
                <label>Order Date:</label>
                <span>{formatDate(selectedPO.order_date)}</span>
              </div>
              <div className="info-item">
                <label>Issue Date:</label>
                <span>{selectedPO.status !== 'draft' ? formatDate(selectedPO.order_date) : 'Not issued'}</span>
              </div>
              <div className="info-item info-item-editable">
                <label>Required Date:</label>
                {editingRequiredDate && (selectedPO.status === 'draft' || selectedPO.status === 'superseded') ? (
                  <div className="edit-inline">
                    <input
                      type="date"
                      value={requiredDateValue}
                      onChange={(e) => setRequiredDateValue(e.target.value)}
                    />
                    <button onClick={handleSaveRequiredDate} className="btn btn-sm btn-primary">Save</button>
                    <button onClick={handleCancelEditRequiredDate} className="btn btn-sm btn-secondary">Cancel</button>
                  </div>
                ) : (
                  <div className="edit-inline">
                    <span>{formatDate(selectedPO.required_date)}</span>
                    {(selectedPO.status === 'draft' || selectedPO.status === 'superseded') && (
                      <button onClick={handleEditRequiredDate} className="btn btn-sm btn-secondary">Edit</button>
                    )}
                  </div>
                )}
              </div>
              <div className="info-item">
                <label>Expected Delivery:</label>
                <span className={isLate(selectedPO.expected_delivery_date, selectedPO.required_date) ? 'late-delivery' : ''}>
                  {formatDate(selectedPO.expected_delivery_date)}
                </span>
              </div>
              <div className="info-item">
                <label>Vendor:</label>
                <span>{selectedPO.vendor_name || `ID: ${selectedPO.vendor_id}`}</span>
              </div>
              {selectedPO.total && (
                <div className="info-item">
                  <label>Total:</label>
                  <span>${selectedPO.total.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>

          <div className="po-items-section">
            <h3>Items</h3>
            <table className="po-items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Description</th>
                  <th>Unit Cost</th>
                  <th>Quantity Ordered</th>
                  <th>Quantity Received</th>
                  <th>Amount</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {selectedPO.items?.map((item) => (
                  <tr key={item.id}>
                    <td>{item.item?.name || 'N/A'}</td>
                    <td>{item.description || 'N/A'}</td>
                    <td>${item.unit_cost?.toFixed(2) || '0.00'}</td>
                    <td>{item.quantity_ordered}</td>
                    <td>{item.quantity_received || 0}</td>
                    <td>${((item.unit_cost || 0) * item.quantity_ordered).toFixed(2)}</td>
                    <td>{item.notes || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="po-tracking-section">
            <h3>Tracking Information</h3>
            <div className="tracking-form">
              <div className="form-group">
                <label>Tracking Number</label>
                <input
                  type="text"
                  value={trackingNumber}
                  onChange={(e) => setTrackingNumber(e.target.value)}
                  placeholder="Enter tracking number"
                />
              </div>
              <div className="form-group">
                <label>Carrier</label>
                <input
                  type="text"
                  value={carrier}
                  onChange={(e) => setCarrier(e.target.value)}
                  placeholder="Enter carrier name"
                />
              </div>
              <button onClick={handleSaveTracking} className="btn btn-primary">Save Tracking Info</button>
            </div>
          </div>

          {selectedPO.notes && (
            <div className="po-notes-section">
              <h3>Notes</h3>
              <p>{selectedPO.notes}</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Convert quantity based on unit display preference
  const convertQuantity = (quantity: number, itemUnit: string) => {
    if (itemUnit === 'ea') return quantity.toFixed(0)
    if (unitDisplay === 'kg' && itemUnit === 'lbs') {
      return (quantity * 0.453592).toFixed(2)
    } else if (unitDisplay === 'lbs' && itemUnit === 'kg') {
      return (quantity * 2.20462).toFixed(2)
    }
    return quantity.toFixed(2)
  }

  const getDisplayUnit = (itemUnit: string) => {
    if (itemUnit === 'ea') return 'ea'
    return unitDisplay
  }

  // Calculate total quantity with unit conversion
  const calculateTotalQuantity = (po: PurchaseOrder) => {
    if (!po.items || po.items.length === 0) return 0
    
    // Get the unit from the first item (assuming all items have the same unit)
    const firstItem = po.items[0]
    const itemUnit = firstItem.item?.unit_of_measure || 'lbs'
    
    const total = po.items.reduce((sum, item) => {
      const qty = item.quantity_ordered || 0
      return sum + qty
    }, 0)
    
    if (itemUnit === 'ea') return total
    
    // Convert to display unit
    if (unitDisplay === 'kg' && itemUnit === 'lbs') {
      return total * 0.453592
    } else if (unitDisplay === 'lbs' && itemUnit === 'kg') {
      return total * 2.20462
    }
    return total
  }

  return (
    <div className="purchase-order-list">
      <div className="po-list-header">
        <h2>Purchase Orders</h2>
        <div className="unit-toggle">
          <label>Display Units:</label>
          <button
            className={`toggle-btn ${unitDisplay === 'lbs' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('lbs')}
          >
            lbs
          </button>
          <button
            className={`toggle-btn ${unitDisplay === 'kg' ? 'active' : ''}`}
            onClick={() => setUnitDisplay('kg')}
          >
            kg
          </button>
        </div>
      </div>

      <div className="po-filters">
        <button
          className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All
        </button>
        <button
          className={`filter-btn ${filter === 'draft' ? 'active' : ''}`}
          onClick={() => setFilter('draft')}
        >
          Draft
        </button>
        <button
          className={`filter-btn ${filter === 'issued' ? 'active' : ''}`}
          onClick={() => setFilter('issued')}
        >
          Issued
        </button>
        <button
          className={`filter-btn ${filter === 'received' ? 'active' : ''}`}
          onClick={() => setFilter('received')}
        >
          Received
        </button>
        <button
          className={`filter-btn ${filter === 'cancelled' ? 'active' : ''}`}
          onClick={() => setFilter('cancelled')}
        >
          Cancelled
        </button>
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : pos.length === 0 ? (
        <div className="empty-state">No purchase orders found</div>
      ) : (
        <table className="po-table">
          <thead>
            <tr>
              <th>PO Number</th>
              <th>Vendor</th>
              <th>Issue Date</th>
              <th>Required Date</th>
              <th>Expected Delivery</th>
              <th>Quantity</th>
              <th>Total</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pos.map((po) => {
              // Calculate total quantity with unit conversion
              const totalQuantity = calculateTotalQuantity(po)
              // Get unit from first item (assuming all items have same unit)
              const displayUnit = po.items && po.items.length > 0 
                ? getDisplayUnit(po.items[0].item?.unit_of_measure || 'lbs')
                : 'lbs'
              
              return (
              <tr key={po.id}>
                <td>
                  {po.po_number}
                  {po.revision_number && po.revision_number > 0 && (
                    <span className="revision-badge"> Rev {po.revision_number}</span>
                  )}
                </td>
                <td>{po.vendor_name || `ID: ${po.vendor_id}`}</td>
                <td>{po.status !== 'draft' ? formatDate(po.order_date) : 'Not issued'}</td>
                <td>{formatDate(po.required_date)}</td>
                <td className={isLate(po.expected_delivery_date, po.required_date) ? 'late-delivery' : ''}>
                  {formatDate(po.expected_delivery_date)}
                </td>
                <td>{parseFloat(totalQuantity.toFixed(2)).toLocaleString()} {displayUnit}</td>
                <td>${po.total?.toFixed(2) || '0.00'}</td>
                <td>
                  <span className={getStatusBadgeClass(po.status)}>{po.status}</span>
                </td>
                <td>
                  <div className="action-buttons">
                    <button onClick={() => handleView(po.id)} className="btn btn-sm btn-primary">View</button>
                    {po.status === 'draft' && (
                      <>
                        <button onClick={() => handleIssue(po.id)} className="btn btn-sm btn-success">Issue</button>
                        <button onClick={() => handleDelete(po.id)} className="btn btn-sm btn-danger">Delete</button>
                      </>
                    )}
                    {(po.status === 'issued' || po.status === 'received') && (
                      <>
                        <button onClick={() => handleRevise(po.id)} className="btn btn-sm btn-warning">Revise</button>
                        <button onClick={() => handleCancel(po.id)} className="btn btn-sm btn-danger">Cancel</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default PurchaseOrderList


