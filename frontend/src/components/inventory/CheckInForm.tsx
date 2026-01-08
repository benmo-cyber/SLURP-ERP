import { useState, useEffect } from 'react'
import { getItems, createLot } from '../../api/inventory'
import { getPurchaseOrders } from '../../api/purchaseOrders'
import { getVendors } from '../../api/quality'
import './CheckInForm.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
}

interface PurchaseOrder {
  id: number
  po_number: string
  vendor_customer_name: string
  carrier?: string
  items?: PurchaseOrderItem[]
}

interface PurchaseOrderItem {
  id: number
  item: {
    id: number
    name: string
    sku: string
  }
  quantity_ordered: number
  quantity_received: number
}

interface Vendor {
  id: number
  name: string
}

interface CheckInRow {
  date: string
  po_number: string
  vendor: string
  carrier: string
  product: string
  product_id: number | null
  product_unit: string
  lot_number: string
  quantity: string
  quantity_unit: string
  po_quantity_ordered: number
  po_quantity_received: number
  short_reason: string
  status: 'accepted' | 'rejected' | 'on_hold'
  coa: boolean
  prod_free_pests: boolean
  carrier_free_pests: boolean
  shipment_accepted: boolean
  initials: string
}

interface CheckInFormProps {
  onClose: () => void
  onSuccess: () => void
}

function CheckInForm({ onClose, onSuccess }: CheckInFormProps) {
  const [items, setItems] = useState<Item[]>([])
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([])
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [rows, setRows] = useState<CheckInRow[]>([
    {
      date: new Date().toISOString().split('T')[0],
      po_number: '',
      vendor: '',
      carrier: '',
      product: '',
      product_id: null,
      product_unit: '',
      lot_number: '',
      quantity: '',
      quantity_unit: 'lbs',
      po_quantity_ordered: 0,
      po_quantity_received: 0,
      short_reason: '',
      status: 'accepted',
      coa: false,
      prod_free_pests: false,
      carrier_free_pests: false,
      shipment_accepted: false,
      initials: '',
    }
  ])

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [itemsData, posData, vendorsData] = await Promise.all([
        getItems(),
        getPurchaseOrders({ status: 'issued' }),
        getVendors()
      ])
      setItems(itemsData)
      setPurchaseOrders(posData)
      setVendors(vendorsData)
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load data. Make sure the backend server is running.')
    } finally {
      setLoading(false)
    }
  }

  const handlePOChange = async (index: number, poNumber: string) => {
    const po = purchaseOrders.find(p => p.po_number === poNumber)
    const updatedRows = [...rows]
    
    if (po) {
      // Load full PO details to get items
      try {
        const { getPurchaseOrder } = await import('../../api/purchaseOrders')
        const fullPO = await getPurchaseOrder(po.id)
        
        updatedRows[index] = {
          ...updatedRows[index],
          po_number: poNumber,
          vendor: fullPO.vendor_customer_name || '',
          carrier: fullPO.carrier || '',
          po_quantity_ordered: 0,
          po_quantity_received: 0,
        }
        
        // If product is already selected, find matching PO item
        if (updatedRows[index].product_id && fullPO.items) {
          const poItem = fullPO.items.find((item: PurchaseOrderItem) => 
            item.item.id === updatedRows[index].product_id
          )
          if (poItem) {
            updatedRows[index].po_quantity_ordered = poItem.quantity_ordered || 0
            updatedRows[index].po_quantity_received = poItem.quantity_received || 0
            console.log('PO Item loaded (PO change):', {
              'quantity_ordered': poItem.quantity_ordered,
              'quantity_received': poItem.quantity_received,
              'item_id': poItem.item?.id,
              'product_id': updatedRows[index].product_id
            })
          } else {
            console.log('PO Item not found for product_id:', updatedRows[index].product_id, 'PO items:', fullPO.items?.map((i: any) => ({ item_id: i.item?.id, quantity_ordered: i.quantity_ordered })))
          }
        }
      } catch (error) {
        console.error('Failed to load PO details:', error)
        updatedRows[index] = {
          ...updatedRows[index],
          po_number: poNumber,
          vendor: po.vendor_customer_name,
          carrier: po.carrier || '',
        }
      }
    } else {
      updatedRows[index] = {
        ...updatedRows[index],
        po_number: poNumber,
        vendor: '',
        carrier: '',
        po_quantity_ordered: 0,
        po_quantity_received: 0,
      }
    }
    
    setRows(updatedRows)
  }

  const handleProductChange = async (index: number, productId: string) => {
    const item = items.find(i => i.id === parseInt(productId))
    const updatedRows = [...rows]
    updatedRows[index] = {
      ...updatedRows[index],
      product: item ? `${item.sku} - ${item.name}` : '',
      product_id: item ? item.id : null,
      product_unit: item ? item.unit_of_measure : '',
      quantity_unit: item ? (item.unit_of_measure === 'kg' ? 'kg' : 'lbs') : 'lbs',
      po_quantity_ordered: 0,
      po_quantity_received: 0,
    }
    
    // If PO is selected, find matching PO item
    if (item && updatedRows[index].po_number) {
      const po = purchaseOrders.find(p => p.po_number === updatedRows[index].po_number)
      if (po) {
        try {
          const { getPurchaseOrder } = await import('../../api/purchaseOrders')
          const fullPO = await getPurchaseOrder(po.id)
          
          if (fullPO.items) {
            const poItem = fullPO.items.find((poItem: PurchaseOrderItem) => 
              poItem.item.id === item.id
            )
            if (poItem) {
              updatedRows[index].po_quantity_ordered = poItem.quantity_ordered || 0
              updatedRows[index].po_quantity_received = poItem.quantity_received || 0
              console.log('PO Item loaded (product change):', {
                'quantity_ordered': poItem.quantity_ordered,
                'quantity_received': poItem.quantity_received,
                'item_id': poItem.item?.id,
                'product_id': item.id
              })
            } else {
              console.log('PO Item not found for product_id:', item.id, 'PO items:', fullPO.items?.map((i: any) => ({ item_id: i.item?.id, quantity_ordered: i.quantity_ordered })))
            }
          }
        } catch (error) {
          console.error('Failed to load PO details:', error)
        }
      }
    }
    
    setRows(updatedRows)
  }

  const handleQuantityUnitChange = (index: number, newUnit: string) => {
    const row = rows[index]
    if (!row.quantity || !row.product_unit) {
      const updatedRows = [...rows]
      updatedRows[index] = {
        ...updatedRows[index],
        quantity_unit: newUnit,
      }
      setRows(updatedRows)
      return
    }
    
    const currentQty = parseFloat(row.quantity) || 0
    let newQty = currentQty
    
    // Convert quantity if needed
    if (row.quantity_unit !== newUnit) {
      if (row.quantity_unit === 'lbs' && newUnit === 'kg') {
        newQty = currentQty / 2.20462
      } else if (row.quantity_unit === 'kg' && newUnit === 'lbs') {
        newQty = currentQty * 2.20462
      }
    }
    
    // Round to whole number
    const roundedQty = Math.round(newQty)
    
    const updatedRows = [...rows]
    updatedRows[index] = {
      ...updatedRows[index],
      quantity: roundedQty.toString(),
      quantity_unit: newUnit,
    }
    setRows(updatedRows)
    
    // Validate quantity after unit change
    setTimeout(() => {
      const finalRow = rows[index]
      if (finalRow.po_quantity_ordered > 0) {
        // Convert PO quantity to display unit for comparison
        let poQtyInDisplayUnit = finalRow.po_quantity_ordered
        if (finalRow.product_unit !== newUnit) {
          if (finalRow.product_unit === 'lbs' && newUnit === 'kg') {
            poQtyInDisplayUnit = finalRow.po_quantity_ordered / 2.20462
          } else if (finalRow.product_unit === 'kg' && newUnit === 'lbs') {
            poQtyInDisplayUnit = finalRow.po_quantity_ordered * 2.20462
          }
        }
        const remainingToReceive = poQtyInDisplayUnit - finalRow.po_quantity_received
        const maxAllowed = Math.round(remainingToReceive)
        
        if (roundedQty > maxAllowed + 0.01) {
          const finalRows = [...rows]
          finalRows[index] = {
            ...finalRows[index],
            quantity: maxAllowed.toString(),
          }
          setRows(finalRows)
        }
      }
    }, 0)
  }

  const validateQuantity = (index: number, quantity: number, unit: string, currentRow: CheckInRow) => {
    if (!currentRow.po_quantity_ordered || !currentRow.product_unit) return false
    
    // Convert PO quantity to display unit for comparison
    let poQtyInDisplayUnit = currentRow.po_quantity_ordered
    if (currentRow.product_unit !== unit) {
      if (currentRow.product_unit === 'lbs' && unit === 'kg') {
        poQtyInDisplayUnit = currentRow.po_quantity_ordered / 2.20462
      } else if (currentRow.product_unit === 'kg' && unit === 'lbs') {
        poQtyInDisplayUnit = currentRow.po_quantity_ordered * 2.20462
      }
    }
    
    const remainingToReceive = poQtyInDisplayUnit - currentRow.po_quantity_received
    const maxAllowed = remainingToReceive
    
    if (quantity > maxAllowed) {
      return false
    }
    return true
  }

  const handleQuantityChange = (index: number, value: string) => {
    // Allow any input - we'll validate and clean on blur
    // Only block negative numbers
    if (value === '' || value === '-') {
      handleRowChange(index, 'quantity', value)
      return
    }
    
    // Allow digits only
    const cleaned = value.replace(/[^\d]/g, '')
    if (cleaned === '') {
      handleRowChange(index, 'quantity', '')
    } else {
      handleRowChange(index, 'quantity', cleaned)
    }
  }
  
  const handleQuantityBlur = (index: number) => {
    // Use a function to get the latest state
    setRows(currentRows => {
      const row = currentRows[index]
      const quantity = parseFloat(row.quantity || '0')
      
      if (isNaN(quantity) || quantity <= 0) {
        return currentRows
      }
      
      // Round to whole number
      const roundedQuantity = Math.round(quantity)
      const updatedRows = [...currentRows]
      updatedRows[index] = {
        ...updatedRows[index],
        quantity: roundedQuantity.toString(),
      }
      
      // Only validate if we have PO data
      if (row.po_quantity_ordered > 0 && row.product_unit) {
        // Convert both PO quantities to display unit for comparison
        let poQtyOrderedInDisplayUnit = row.po_quantity_ordered
        let poQtyReceivedInDisplayUnit = row.po_quantity_received || 0
        
        // Convert ordered quantity if needed
        if (row.product_unit !== row.quantity_unit) {
          if (row.product_unit === 'lbs' && row.quantity_unit === 'kg') {
            poQtyOrderedInDisplayUnit = row.po_quantity_ordered / 2.20462
            poQtyReceivedInDisplayUnit = (row.po_quantity_received || 0) / 2.20462
          } else if (row.product_unit === 'kg' && row.quantity_unit === 'lbs') {
            poQtyOrderedInDisplayUnit = row.po_quantity_ordered * 2.20462
            poQtyReceivedInDisplayUnit = (row.po_quantity_received || 0) * 2.20462
          }
        }
        
        const remainingToReceive = poQtyOrderedInDisplayUnit - poQtyReceivedInDisplayUnit
        const maxAllowed = Math.round(remainingToReceive)
        
        // Debug logging
        console.log('Validation Debug:', {
          'row.po_quantity_ordered': row.po_quantity_ordered,
          'row.po_quantity_received': row.po_quantity_received,
          'row.product_unit': row.product_unit,
          'row.quantity_unit': row.quantity_unit,
          'poQtyOrderedInDisplayUnit': poQtyOrderedInDisplayUnit,
          'poQtyReceivedInDisplayUnit': poQtyReceivedInDisplayUnit,
          'remainingToReceive': remainingToReceive,
          'maxAllowed': maxAllowed,
          'roundedQuantity': roundedQuantity
        })
        
        // Only show error if quantity actually exceeds remaining
        // Use a small tolerance for floating point comparison (0.01)
        // Don't validate if remaining is 0 or negative - this might be a data loading issue
        if (remainingToReceive > 0 && roundedQuantity > maxAllowed + 0.01) {
          alert(`Quantity cannot exceed remaining PO quantity (${maxAllowed} ${row.quantity_unit}). Remaining: ${maxAllowed} ${row.quantity_unit}`)
          updatedRows[index] = {
            ...updatedRows[index],
            quantity: maxAllowed.toString(),
          }
          return updatedRows
        }
        
        // If remaining is 0 or negative, log a warning but don't block - might be data issue
        if (remainingToReceive <= 0 && roundedQuantity > 0) {
          console.warn('Warning: Remaining PO quantity is 0 or negative, but user entered quantity. This might indicate a data loading issue.', {
            'po_quantity_ordered': row.po_quantity_ordered,
            'po_quantity_received': row.po_quantity_received,
            'remainingToReceive': remainingToReceive
          })
          // Don't block - allow the user to proceed and let backend handle validation
        }
      }
      
      return updatedRows
    })
  }

  const handleRowChange = (index: number, field: keyof CheckInRow, value: any) => {
    const updatedRows = [...rows]
    updatedRows[index] = {
      ...updatedRows[index],
      [field]: value
    }
    setRows(updatedRows)
  }

  const addRow = () => {
    setRows([...rows, {
      date: new Date().toISOString().split('T')[0],
      po_number: '',
      vendor: '',
      carrier: '',
      product: '',
      product_id: null,
      product_unit: '',
      lot_number: '',
      quantity: '',
      quantity_unit: 'lbs',
      po_quantity_ordered: 0,
      po_quantity_received: 0,
      short_reason: '',
      status: 'accepted',
      coa: false,
      prod_free_pests: false,
      carrier_free_pests: false,
      shipment_accepted: false,
      initials: '',
    }])
  }

  const removeRow = (index: number) => {
    if (rows.length > 1) {
      setRows(rows.filter((_, i) => i !== index))
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Validate all rows
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i]
      if (!row.date || !row.po_number || !row.product_id || !row.quantity || 
          !row.status || !row.coa || !row.prod_free_pests || !row.carrier_free_pests || 
          !row.shipment_accepted || !row.initials) {
        alert(`Please fill in all required fields in row ${i + 1}`)
        return
      }
    }

    try {
      setSubmitting(true)
      
      // Submit each row as a separate lot
      for (const row of rows) {
        // Convert quantity to item's unit of measure if needed
        let quantity = parseFloat(row.quantity) || 0
        
        if (quantity <= 0) {
          alert(`Row ${rows.indexOf(row) + 1}: Quantity must be greater than 0`)
          return
        }
        
        const item = items.find(i => i.id === row.product_id)
        
        if (!item) {
          alert(`Row ${rows.indexOf(row) + 1}: Item not found`)
          return
        }
        
        if (item && row.quantity_unit !== item.unit_of_measure) {
          if (row.quantity_unit === 'lbs' && item.unit_of_measure === 'kg') {
            quantity = quantity / 2.20462
          } else if (row.quantity_unit === 'kg' && item.unit_of_measure === 'lbs') {
            quantity = quantity * 2.20462
          }
        }
        
        // Ensure quantity is still valid after conversion
        if (isNaN(quantity) || quantity <= 0) {
          alert(`Row ${rows.indexOf(row) + 1}: Invalid quantity after unit conversion`)
          return
        }
        
        // Convert date to ISO string with time
        const receivedDate = row.date ? new Date(row.date + 'T00:00:00').toISOString() : new Date().toISOString()
        
        const checkInData = {
          item_id: row.product_id,
          quantity: quantity,
          received_date: receivedDate,
          po_number: row.po_number || null,
          status: row.status,
          short_reason: row.short_reason && row.short_reason.trim() ? row.short_reason.trim() : null,
        }
        
        console.log('Submitting check-in data:', checkInData)
        await createLot(checkInData)
      }
      
      alert('Materials checked in successfully!')
      onSuccess()
      onClose()
    } catch (error: any) {
      console.error('Failed to check in materials:', error)
      console.error('Error response:', error.response?.data)
      const errorMessage = error.response?.data?.detail || 
                          error.response?.data?.message || 
                          (error.response?.data && JSON.stringify(error.response.data)) ||
                          error.message || 
                          'Failed to check in materials'
      alert(errorMessage)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content checkin-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Check In Materials</h2>
            <button onClick={onClose} className="close-btn">×</button>
          </div>
          <div className="modal-body">
            <div className="loading">Loading data...</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content checkin-modal checkin-table-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Check In Materials</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="checkin-form">
          <div className="checkin-table-wrapper">
            <table className="checkin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>PO Number</th>
                  <th>Vendor</th>
                  <th>Carrier</th>
                  <th>Product</th>
                  <th>Lot #</th>
                  <th>Quantity</th>
                  <th>Status</th>
                  <th>Short Reason</th>
                  <th>CoA (*)</th>
                  <th>Prod. Free Pests, Odors and Clean (*)</th>
                  <th>Carrier Free of Pests, Odors, Clean, Secured Load (*)</th>
                  <th>Shipment accepted and stored as required (*)</th>
                  <th>Initials</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        type="date"
                        value={row.date}
                        onChange={(e) => handleRowChange(index, 'date', e.target.value)}
                        required
                        className="table-input"
                      />
                    </td>
                    <td>
                      <select
                        value={row.po_number}
                        onChange={(e) => handlePOChange(index, e.target.value)}
                        required
                        className="table-input"
                      >
                        <option value="">Select PO...</option>
                        {purchaseOrders.map((po) => (
                          <option key={po.id} value={po.po_number}>
                            {po.po_number}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={row.vendor}
                        onChange={(e) => handleRowChange(index, 'vendor', e.target.value)}
                        required
                        className="table-input"
                        readOnly
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={row.carrier}
                        onChange={(e) => handleRowChange(index, 'carrier', e.target.value)}
                        required
                        className="table-input"
                      />
                    </td>
                    <td>
                      <select
                        value={row.product_id || ''}
                        onChange={(e) => handleProductChange(index, e.target.value)}
                        required
                        className="table-input"
                      >
                        <option value="">Select Product...</option>
                        {items.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.sku} - {item.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="text"
                        value={row.lot_number}
                        onChange={(e) => handleRowChange(index, 'lot_number', e.target.value)}
                        placeholder="Auto-generated"
                        className="table-input"
                        readOnly
                      />
                    </td>
                    <td>
                      <div className="quantity-input-group">
                        <input
                          type="number"
                          step="1"
                          min="0"
                          value={row.quantity}
                          onChange={(e) => handleQuantityChange(index, e.target.value)}
                          onBlur={() => handleQuantityBlur(index)}
                          required
                          className="table-input quantity-input"
                        />
                        {row.product_unit && (row.product_unit === 'lbs' || row.product_unit === 'kg') && (
                          <div className="unit-toggle-group">
                            <button
                              type="button"
                              className={`unit-toggle-btn ${row.quantity_unit === 'lbs' ? 'active' : ''}`}
                              onClick={() => handleQuantityUnitChange(index, 'lbs')}
                            >
                              lbs
                            </button>
                            <button
                              type="button"
                              className={`unit-toggle-btn ${row.quantity_unit === 'kg' ? 'active' : ''}`}
                              onClick={() => handleQuantityUnitChange(index, 'kg')}
                            >
                              kg
                            </button>
                          </div>
                        )}
                      </div>
                      {row.po_quantity_ordered > 0 && (() => {
                        // Convert to display unit for hint
                        let poQtyOrderedInDisplayUnit = row.po_quantity_ordered
                        let poQtyReceivedInDisplayUnit = row.po_quantity_received
                        if (row.product_unit !== row.quantity_unit) {
                          if (row.product_unit === 'lbs' && row.quantity_unit === 'kg') {
                            poQtyOrderedInDisplayUnit = row.po_quantity_ordered / 2.20462
                            poQtyReceivedInDisplayUnit = row.po_quantity_received / 2.20462
                          } else if (row.product_unit === 'kg' && row.quantity_unit === 'lbs') {
                            poQtyOrderedInDisplayUnit = row.po_quantity_ordered * 2.20462
                            poQtyReceivedInDisplayUnit = row.po_quantity_received * 2.20462
                          }
                        }
                        const remainingToReceive = poQtyOrderedInDisplayUnit - poQtyReceivedInDisplayUnit
                        return (
                          <small className="po-quantity-hint">
                            PO: {Math.round(poQtyOrderedInDisplayUnit)} {row.quantity_unit}, Received: {Math.round(poQtyReceivedInDisplayUnit)} {row.quantity_unit}, Remaining: {Math.round(remainingToReceive)} {row.quantity_unit}
                          </small>
                        )
                      })()}
                    </td>
                    <td>
                      <select
                        value={row.status}
                        onChange={(e) => handleRowChange(index, 'status', e.target.value)}
                        required
                        className="table-input"
                      >
                        <option value="accepted">Accepted</option>
                        <option value="rejected">Rejected</option>
                        <option value="on_hold">On Hold</option>
                      </select>
                    </td>
                    <td>
                      {row.po_quantity_ordered > 0 && (() => {
                        // Convert both to display unit for comparison
                        let poQtyOrderedInDisplayUnit = row.po_quantity_ordered
                        let poQtyReceivedInDisplayUnit = row.po_quantity_received
                        if (row.product_unit !== row.quantity_unit) {
                          if (row.product_unit === 'lbs' && row.quantity_unit === 'kg') {
                            poQtyOrderedInDisplayUnit = row.po_quantity_ordered / 2.20462
                            poQtyReceivedInDisplayUnit = row.po_quantity_received / 2.20462
                          } else if (row.product_unit === 'kg' && row.quantity_unit === 'lbs') {
                            poQtyOrderedInDisplayUnit = row.po_quantity_ordered * 2.20462
                            poQtyReceivedInDisplayUnit = row.po_quantity_received * 2.20462
                          }
                        }
                        const remainingToReceive = poQtyOrderedInDisplayUnit - poQtyReceivedInDisplayUnit
                        const enteredQty = parseFloat(row.quantity || '0')
                        // Show reason field if quantity is less than remaining to receive
                        if (enteredQty > 0 && enteredQty < remainingToReceive) {
                          return (
                            <input
                              type="text"
                              value={row.short_reason}
                              onChange={(e) => handleRowChange(index, 'short_reason', e.target.value)}
                              placeholder="Reason (damage, short shipped, etc.)"
                              className="table-input short-reason-input"
                            />
                          )
                        }
                        return null
                      })()}
                    </td>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={row.coa}
                        onChange={(e) => handleRowChange(index, 'coa', e.target.checked)}
                        required
                      />
                    </td>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={row.prod_free_pests}
                        onChange={(e) => handleRowChange(index, 'prod_free_pests', e.target.checked)}
                        required
                      />
                    </td>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={row.carrier_free_pests}
                        onChange={(e) => handleRowChange(index, 'carrier_free_pests', e.target.checked)}
                        required
                      />
                    </td>
                    <td className="checkbox-cell">
                      <input
                        type="checkbox"
                        checked={row.shipment_accepted}
                        onChange={(e) => handleRowChange(index, 'shipment_accepted', e.target.checked)}
                        required
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={row.initials}
                        onChange={(e) => handleRowChange(index, 'initials', e.target.value.toUpperCase())}
                        required
                        className="table-input initials-input"
                        maxLength={5}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => removeRow(index)}
                        className="btn-remove-row"
                        disabled={rows.length === 1}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="checkin-actions">
            <button type="button" onClick={addRow} className="btn btn-secondary">
              Add Row
            </button>
            <div className="form-actions">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? 'Checking In...' : 'Check In'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CheckInForm
