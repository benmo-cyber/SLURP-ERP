import { useState, useEffect, useMemo, useRef } from 'react'
import {
  getPurchaseOrders,
  getPurchaseOrder,
  updatePurchaseOrder,
  updatePurchaseOrderItem,
  issuePurchaseOrder,
  revisePurchaseOrder,
  cancelPurchaseOrder,
  deletePurchaseOrder,
  updateDeliveryFromTracking,
  getPurchaseOrderPdfUrl,
} from '../../api/purchaseOrders'
import {
  bulkReverseCheckIn,
  getLotsByPurchaseOrder,
  reverseCheckIn,
  type BulkReverseCheckInResult,
} from '../../api/inventory'
import { useAuth } from '../../context/AuthContext'
import { getVendors, getVendorContacts } from '../../api/quality'
import { formatCurrency, formatNumber } from '../../utils/formatNumber'
import { formatAppDate, formatAppDateFromYmd } from '../../utils/appDateFormat'
import { useGodMode } from '../../context/GodModeContext'
import './PurchaseOrderList.css'

/** Backend returns { error: '...' }; DRF uses { detail: ... }; surface both. */
function formatApiError(err: unknown): string {
  const e = err as { response?: { data?: Record<string, unknown> }; message?: string }
  const d = e?.response?.data
  if (!d) return e?.message || 'Request failed'
  if (typeof d === 'string') return d
  if (typeof d.error === 'string') return d.error
  if (typeof d.detail === 'string') return d.detail
  if (Array.isArray(d.detail)) return JSON.stringify(d.detail)
  if (typeof d.message === 'string') return d.message
  if (Array.isArray(d.non_field_errors)) return (d.non_field_errors as string[]).join(' ')
  try {
    return JSON.stringify(d)
  } catch {
    return 'Request failed'
  }
}

/** Normalize API order_date (ISO) to YYYY-MM-DD for <input type="date"> */
function poOrderDateToYmd(orderDate: string | undefined, fallbackYmd: string): string {
  if (!orderDate || typeof orderDate !== 'string') return fallbackYmd
  const m = orderDate.trim().match(/^(\d{4}-\d{2}-\d{2})/)
  if (m) return m[1]
  const t = Date.parse(orderDate)
  if (!Number.isNaN(t)) {
    const d = new Date(t)
    return (
      d.getFullYear() +
      '-' +
      String(d.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(d.getDate()).padStart(2, '0')
    )
  }
  return fallbackYmd
}

interface PurchaseOrderItem {
  id: number
  item: {
    id: number
    name: string
    sku: string
    vendor_item_name?: string
    vendor_item_number?: string | null
    display_name_for_vendor?: string
    unit_of_measure?: string
  }
  description?: string
  unit_cost: number
  quantity_ordered: number
  quantity_received: number
  notes: string
  /** UoM for qty + unit price on this line (e.g. kg when item master is lbs) */
  order_uom?: string | null
}

interface ServiceVendor {
  id: number
  name: string
  is_service_vendor?: boolean
  service_vendor_type?: string | null
}

interface NotifyPartyContact {
  id: number
  vendor?: { name?: string }
  vendor_name?: string
  name: string
  emails?: string[]
  phone?: string
  location_label?: string
  notes?: string
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
  discount?: number
  shipping_cost?: number
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
  drop_ship?: boolean
  fulfillment_sales_order?: number | null
  notes?: string
  notify_party_contacts?: { id: number; name: string; emails?: string[]; phone?: string; location_label?: string; notes?: string; vendor?: { name: string } }[]
}

/** Draft PO detail: editable line fields */
type PoLineDraft = { unit_cost: string; notes: string; quantity: string; order_uom: string }

/** Vendor-facing description: name + optional vendor catalog # */
interface PoLinkedLot {
  id: number
  lot_number: string
  quantity: number
  quantity_remaining: number
  po_number?: string
  po_tracking_number?: string
  po_carrier?: string
  received_date?: string
  item: {
    id: number
    sku: string
    name: string
    unit_of_measure?: string
  }
  pack_size_obj?: { pack_size: number; pack_size_unit: string; description?: string }
  committed_to_sales_qty?: number
  committed_to_production_qty?: number
}

/** Matches backend reverse-check-in rule (unused lot only; API uses DB remaining vs received qty). */
function lotEligibleForUnfk(lot: PoLinkedLot): boolean {
  const q = lot.quantity ?? 0
  const r = lot.quantity_remaining ?? 0
  return Math.abs(q - r) < 1e-3
}

function formatPoLineVendorLabel(
  lineItem: PurchaseOrderItem['item'] | undefined,
  fallbackDescription?: string
): string {
  const name = lineItem
    ? (lineItem.display_name_for_vendor || lineItem.vendor_item_name || lineItem.name || '').trim()
    : ''
  const base = name || (fallbackDescription || '').trim() || 'N/A'
  const num = (lineItem?.vendor_item_number || '').trim()
  return num && base !== 'N/A' ? `${base} (${num})` : base
}

function PurchaseOrderList() {
  const { user } = useAuth()
  const [pos, setPos] = useState<PurchaseOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [selectedPO, setSelectedPO] = useState<PurchaseOrder | null>(null)
  const [editingRequiredDate, setEditingRequiredDate] = useState(false)
  const [requiredDateValue, setRequiredDateValue] = useState<string>('')
  const [trackingNumber, setTrackingNumber] = useState<string>('')
  const [carrier, setCarrier] = useState<string>('')
  const [unitDisplay, setUnitDisplay] = useState<'lbs' | 'kg'>('lbs')
  type POSortKey = 'po_number' | 'vendor' | 'order_date' | 'required_date' | 'expected_delivery_date' | 'total' | 'status' | null
  const [sort, setSort] = useState<{ key: POSortKey; dir: 'asc' | 'desc' }>({ key: 'order_date', dir: 'desc' })

  useEffect(() => {
    loadPOs()
  }, [filter])

  const [discountValue, setDiscountValue] = useState<string>('')
  const [shippingCostValue, setShippingCostValue] = useState<string>('')
  const [savingTotals, setSavingTotals] = useState(false)

  // Draft-only notify party editor (contacts can come from multiple service vendors)
  const [serviceVendors, setServiceVendors] = useState<ServiceVendor[]>([])
  const [notifyPartyAddVendorId, setNotifyPartyAddVendorId] = useState<string>('')
  const [notifyPartyAddContacts, setNotifyPartyAddContacts] = useState<NotifyPartyContact[]>([])
  const [notifyPartyContactIdsDraft, setNotifyPartyContactIdsDraft] = useState<number[]>([])
  const [notifyPartyContactsCache, setNotifyPartyContactsCache] = useState<Record<number, NotifyPartyContact>>({})
  const [notifyPartyContactsLoading, setNotifyPartyContactsLoading] = useState(false)
  const [savingNotifyParties, setSavingNotifyParties] = useState(false)

  /** Draft PO line edits — qty, UoM, unit cost, line notes */
  const [poLineDrafts, setPoLineDrafts] = useState<Record<number, PoLineDraft>>({})
  const [savingLineId, setSavingLineId] = useState<number | null>(null)
  const [poNotesDraft, setPoNotesDraft] = useState('')
  const [savingPoNotes, setSavingPoNotes] = useState(false)

  const { godModeOn, canUseGodMode, maxDateForEntry, minDateForEntry } = useGodMode()
  const todayYmd = useMemo(() => {
    const d = new Date()
    return (
      d.getFullYear() +
      '-' +
      String(d.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(d.getDate()).padStart(2, '0')
    )
  }, [])

  const [issueModalPo, setIssueModalPo] = useState<PurchaseOrder | null>(null)
  const [issueDateValue, setIssueDateValue] = useState('')
  const [issuingPoId, setIssuingPoId] = useState<number | null>(null)
  const [editingOrderDate, setEditingOrderDate] = useState(false)
  const [orderDateDraftValue, setOrderDateDraftValue] = useState('')
  const [editingPoNumber, setEditingPoNumber] = useState(false)
  const [poNumberDraft, setPoNumberDraft] = useState('')
  const [poItemsDeeperOpen, setPoItemsDeeperOpen] = useState(false)
  const [poReceiptLots, setPoReceiptLots] = useState<PoLinkedLot[] | null>(null)
  const [poReceiptLotsLoading, setPoReceiptLotsLoading] = useState(false)
  const [unfkLotId, setUnfkLotId] = useState<number | null>(null)
  const [bulkUnfkBusy, setBulkUnfkBusy] = useState(false)
  const [unfkModalSelectedIds, setUnfkModalSelectedIds] = useState<Set<number>>(new Set())
  const unfkSelectionPoIdRef = useRef<number | null>(null)
  /** List row → pick which receipt lot to reverse (same actions as Deeper table). */
  const [unfkModal, setUnfkModal] = useState<{
    po: PurchaseOrder
    lots: PoLinkedLot[]
    loading: boolean
  } | null>(null)
  const [poListDeeperOpen, setPoListDeeperOpen] = useState(false)
  /** Auto-expand receipt / reverse-check-in section once when opening a PO that has check-ins */
  const unfkAutoExpandedForPoId = useRef<number | null>(null)

  useEffect(() => {
    setPoListDeeperOpen(false)
  }, [filter])

  useEffect(() => {
    const primary = pos.filter(
      (p) => p.status !== 'received' && p.status !== 'completed'
    )
    const deeper = pos.filter(
      (p) => p.status === 'received' || p.status === 'completed'
    )
    if (primary.length === 0 && deeper.length > 0) {
      setPoListDeeperOpen(true)
    }
  }, [pos, filter])

  useEffect(() => {
    setPoItemsDeeperOpen(false)
    setPoReceiptLots(null)
    setPoReceiptLotsLoading(false)
  }, [selectedPO?.id])

  /** After reset above: open Deeper once for POs with receipt qty so reverse check-in is visible */
  useEffect(() => {
    if (!selectedPO) {
      unfkAutoExpandedForPoId.current = null
      return
    }
    if (selectedPO.status === 'draft') return
    if (unfkAutoExpandedForPoId.current === selectedPO.id) return
    const hasReceipts = (selectedPO.items || []).some((i) => (i.quantity_received || 0) > 0)
    if (!hasReceipts) return
    unfkAutoExpandedForPoId.current = selectedPO.id
    setPoItemsDeeperOpen(true)
    setPoReceiptLotsLoading(true)
    getLotsByPurchaseOrder(selectedPO.po_number)
      .then((data) => setPoReceiptLots(Array.isArray(data) ? data : []))
      .catch(() => setPoReceiptLots([]))
      .finally(() => setPoReceiptLotsLoading(false))
  }, [selectedPO?.id, selectedPO?.status, selectedPO?.po_number])

  useEffect(() => {
    if (!unfkModal) {
      unfkSelectionPoIdRef.current = null
      return
    }
    if (unfkModal.loading) return
    const pid = unfkModal.po.id
    const eligibleIds = unfkModal.lots.filter(lotEligibleForUnfk).map((l) => l.id)
    if (unfkSelectionPoIdRef.current !== pid) {
      unfkSelectionPoIdRef.current = pid
      setUnfkModalSelectedIds(new Set(eligibleIds))
    } else {
      setUnfkModalSelectedIds((prev) => {
        const eligible = new Set(eligibleIds)
        const next = new Set<number>()
        prev.forEach((id) => {
          if (eligible.has(id)) next.add(id)
        })
        return next
      })
    }
  }, [unfkModal])

  useEffect(() => {
    if (selectedPO) {
      setTrackingNumber(selectedPO.tracking_number || '')
      setCarrier(selectedPO.carrier || '')
      setPoNotesDraft(selectedPO.notes || '')
      if (selectedPO.status === 'draft' && selectedPO.items?.length) {
        const next: Record<number, PoLineDraft> = {}
        selectedPO.items.forEach((it) => {
          const native = it.item?.unit_of_measure || 'lbs'
          const savedOrderUom = (it.order_uom || '').trim()
          next[it.id] = {
            unit_cost: it.unit_cost != null ? String(it.unit_cost) : '',
            notes: it.notes || '',
            quantity: String(it.quantity_ordered ?? ''),
            order_uom: savedOrderUom || native,
          }
        })
        setPoLineDrafts(next)
      } else {
        setPoLineDrafts({})
      }
      setRequiredDateValue(
        selectedPO.required_date ? selectedPO.required_date.trim().slice(0, 10) : ''
      )
      setDiscountValue(selectedPO.discount != null ? String(selectedPO.discount) : '')
      setShippingCostValue(selectedPO.shipping_cost != null ? String(selectedPO.shipping_cost) : '')
      setOrderDateDraftValue(selectedPO.order_date ? selectedPO.order_date.slice(0, 10) : todayYmd)
      setEditingOrderDate(false)
      setPoNumberDraft(selectedPO.po_number || '')
      setEditingPoNumber(false)
    }
  }, [selectedPO, todayYmd])

  useEffect(() => {
    // Load service vendors once for the draft-only notify party editor.
    const load = async () => {
      try {
        const data = await getVendors()
        const list = Array.isArray(data) ? data : []
        setServiceVendors(list.filter((v: ServiceVendor) => v.is_service_vendor))
      } catch {
        setServiceVendors([])
      }
    }
    load()
  }, [])

  useEffect(() => {
    if (!selectedPO) return

    const contacts = selectedPO.notify_party_contacts || []
    setNotifyPartyContactIdsDraft(contacts.map((c) => c.id))

    const cache: Record<number, NotifyPartyContact> = {}
    contacts.forEach((c) => {
      const vendorName = c.vendor_name || c.vendor?.name
      cache[c.id] = {
        id: c.id,
        vendor_name: vendorName,
        name: c.name,
        emails: c.emails || [],
        phone: c.phone,
        location_label: c.location_label,
        notes: c.notes,
      }
    })
    setNotifyPartyContactsCache(cache)

    setNotifyPartyAddVendorId('')
    setNotifyPartyAddContacts([])
    setNotifyPartyContactsLoading(false)
  }, [selectedPO])

  const toggleNotifyPartyContact = (contactId: number) => {
    setNotifyPartyContactIdsDraft((prev) =>
      prev.includes(contactId) ? prev.filter((id) => id !== contactId) : [...prev, contactId]
    )
  }

  const loadNotifyPartyContacts = async (vendorId: number) => {
    try {
      setNotifyPartyContactsLoading(true)
      const list = await getVendorContacts(vendorId)
      const arr = Array.isArray(list) ? list : []
      setNotifyPartyAddContacts(arr)

      setNotifyPartyContactsCache((prev) => {
        const next = { ...prev }
        ;(arr as any[]).forEach((c) => {
          if (!c) return
          const vendorName = c.vendor_name || c.vendor?.name
          next[c.id] = {
            id: c.id,
            vendor_name: vendorName,
            name: c.name,
            emails: c.emails || [],
            phone: c.phone,
            location_label: c.location_label,
            notes: c.notes,
          }
        })
        return next
      })
    } finally {
      setNotifyPartyContactsLoading(false)
    }
  }

  const handleSaveNotifyParties = async () => {
    if (!selectedPO) return
    try {
      setSavingNotifyParties(true)
      await updatePurchaseOrder(selectedPO.id, {
        notify_party_contact_ids: notifyPartyContactIdsDraft,
      })
      alert('Notify party contacts updated')
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: any) {
      console.error('Failed to update notify parties:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update notify parties')
    } finally {
      setSavingNotifyParties(false)
    }
  }

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

  const sortedPos = [...pos].sort((a, b) => {
    if (!sort.key) return 0
    let cmp = 0
    switch (sort.key) {
      case 'po_number': cmp = (a.po_number || '').localeCompare(b.po_number || ''); break
      case 'vendor': cmp = (a.vendor_name || '').localeCompare(b.vendor_name || ''); break
      case 'order_date': cmp = new Date(a.order_date).getTime() - new Date(b.order_date).getTime(); break
      case 'required_date': cmp = new Date(a.required_date || 0).getTime() - new Date(b.required_date || 0).getTime(); break
      case 'expected_delivery_date': cmp = new Date(a.expected_delivery_date || 0).getTime() - new Date(b.expected_delivery_date || 0).getTime(); break
      case 'total': cmp = (a.total ?? 0) - (b.total ?? 0); break
      case 'status': cmp = (a.status || '').localeCompare(b.status || ''); break
      default: return 0
    }
    return sort.dir === 'asc' ? cmp : -cmp
  })

  const handleSort = (key: NonNullable<POSortKey>) => {
    setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }))
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

  const runIssueWithConfirm = async (id: number) => {
    if (!confirm('Are you sure you want to issue this purchase order? This will update inventory.')) {
      return
    }
    try {
      setIssuingPoId(id)
      await issuePurchaseOrder(id)
      alert('Purchase order issued successfully')
      loadPOs()
      if (selectedPO?.id === id) {
        setSelectedPO(null)
      }
    } catch (error: unknown) {
      console.error('Failed to issue purchase order:', error)
      alert(formatApiError(error))
    } finally {
      setIssuingPoId(null)
    }
  }

  const handleIssue = (po: PurchaseOrder) => {
    if (godModeOn && canUseGodMode) {
      setIssueModalPo(po)
      setIssueDateValue(poOrderDateToYmd(po.order_date, todayYmd))
      return
    }
    void runIssueWithConfirm(po.id)
  }

  const submitIssueFromModal = async () => {
    if (!issueModalPo) return
    const ymd = (issueDateValue || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) {
      alert('Choose a valid issue date (YYYY-MM-DD).')
      return
    }
    try {
      setIssuingPoId(issueModalPo.id)
      await issuePurchaseOrder(issueModalPo.id, { issue_date: ymd })
      alert('Purchase order issued successfully')
      setIssueModalPo(null)
      loadPOs()
      if (selectedPO?.id === issueModalPo.id) {
        setSelectedPO(null)
      }
    } catch (error: unknown) {
      console.error('Failed to issue purchase order:', error)
      alert(formatApiError(error))
    } finally {
      setIssuingPoId(null)
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
    setRequiredDateValue(
      selectedPO?.required_date ? selectedPO.required_date.trim().slice(0, 10) : ''
    )
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
    setRequiredDateValue(
      selectedPO?.required_date ? selectedPO.required_date.trim().slice(0, 10) : ''
    )
  }

  const handleSaveOrderDate = async () => {
    if (!selectedPO || selectedPO.status !== 'draft') return
    try {
      await updatePurchaseOrder(selectedPO.id, {
        order_date: `${orderDateDraftValue}T12:00:00`,
      })
      setEditingOrderDate(false)
      alert('PO / issue date updated')
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: any) {
      console.error('Failed to update PO date:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update PO date')
    }
  }

  const handleCancelEditOrderDate = () => {
    setEditingOrderDate(false)
    setOrderDateDraftValue(selectedPO?.order_date ? selectedPO.order_date.slice(0, 10) : todayYmd)
  }

  const handleSavePoNumber = async () => {
    if (!selectedPO) return
    const next = poNumberDraft.trim()
    if (!next) {
      alert('PO number cannot be empty.')
      return
    }
    try {
      await updatePurchaseOrder(selectedPO.id, { po_number: next })
      setEditingPoNumber(false)
      alert('PO number updated')
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: any) {
      console.error('Failed to update PO number:', error)
      const msg =
        error.response?.data?.po_number ||
        error.response?.data?.detail ||
        error.response?.data?.message ||
        'Failed to update PO number'
      alert(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  const handleCancelEditPoNumber = () => {
    setEditingPoNumber(false)
    setPoNumberDraft(selectedPO?.po_number || '')
  }

  const handleSaveDiscountAndShipping = async () => {
    if (!selectedPO) return
    const discount = discountValue === '' ? 0 : parseFloat(discountValue)
    const shippingCost = shippingCostValue === '' ? 0 : parseFloat(shippingCostValue)
    if (isNaN(discount) || isNaN(shippingCost)) {
      alert('Please enter valid numbers for discount and shipping.')
      return
    }
    try {
      setSavingTotals(true)
      await updatePurchaseOrder(selectedPO.id, {
        discount: discount,
        shipping_cost: shippingCost,
      })
      alert('Discount and shipping updated.')
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: any) {
      console.error('Failed to update discount/shipping:', error)
      alert(error.response?.data?.detail || error.response?.data?.message || 'Failed to update')
    } finally {
      setSavingTotals(false)
    }
  }

  const toggleDraftLineUom = (itemId: number, newUom: 'lbs' | 'kg') => {
    setPoLineDrafts((prev) => {
      const d = prev[itemId]
      if (!d) return prev
      if (d.order_uom !== 'lbs' && d.order_uom !== 'kg') return prev
      if (d.order_uom === newUom) return prev
      let qty = parseFloat(d.quantity) || 0
      let uc = parseFloat(d.unit_cost) || 0
      if (d.order_uom === 'lbs' && newUom === 'kg') {
        qty = qty / 2.20462
        uc = uc * 2.20462
      } else if (d.order_uom === 'kg' && newUom === 'lbs') {
        qty = qty * 2.20462
        uc = uc / 2.20462
      }
      return {
        ...prev,
        [itemId]: {
          ...d,
          order_uom: newUom,
          quantity: String(Math.round(qty * 100000) / 100000),
          unit_cost: String(Math.round(uc * 1000000) / 1000000),
        },
      }
    })
  }

  const handleSavePoLine = async (itemId: number) => {
    if (!selectedPO) return
    const d = poLineDrafts[itemId]
    if (!d) return
    const uc = parseFloat(d.unit_cost)
    if (Number.isNaN(uc) || uc < 0) {
      alert('Enter a valid unit cost (0 or greater).')
      return
    }
    const qty = parseFloat(d.quantity)
    if (Number.isNaN(qty) || qty <= 0) {
      alert('Enter a valid quantity greater than 0.')
      return
    }
    try {
      setSavingLineId(itemId)
      await updatePurchaseOrderItem(itemId, {
        unit_cost: uc,
        notes: d.notes.trim() || null,
        quantity_ordered: qty,
        order_uom: d.order_uom.trim() || null,
      })
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: unknown) {
      alert(formatApiError(error))
    } finally {
      setSavingLineId(null)
    }
  }

  const handleSavePoNotes = async () => {
    if (!selectedPO) return
    try {
      setSavingPoNotes(true)
      await updatePurchaseOrder(selectedPO.id, { notes: poNotesDraft.trim() || null })
      await loadPOs()
      const updated = await getPurchaseOrder(selectedPO.id)
      setSelectedPO(updated)
    } catch (error: unknown) {
      alert(formatApiError(error))
    } finally {
      setSavingPoNotes(false)
    }
  }

  const refreshPoReceiptLots = async () => {
    if (!selectedPO) return
    setPoReceiptLotsLoading(true)
    try {
      const data = await getLotsByPurchaseOrder(selectedPO.po_number)
      setPoReceiptLots(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('Failed to load lots for PO:', e)
      setPoReceiptLots([])
    } finally {
      setPoReceiptLotsLoading(false)
    }
  }

  const togglePoItemsDeeper = async () => {
    if (!selectedPO || selectedPO.status === 'draft') return
    if (poItemsDeeperOpen) {
      setPoItemsDeeperOpen(false)
      return
    }
    setPoItemsDeeperOpen(true)
    if (poReceiptLots === null) {
      await refreshPoReceiptLots()
    }
  }

  const openUnfkModalForPo = (po: PurchaseOrder) => {
    setUnfkModal({ po, lots: [], loading: true })
    void getLotsByPurchaseOrder(po.po_number)
      .then((data) => {
        const arr = Array.isArray(data) ? data : []
        setUnfkModal((m) => (m && m.po.id === po.id ? { ...m, lots: arr, loading: false } : m))
      })
      .catch(() => {
        setUnfkModal((m) => (m && m.po.id === po.id ? { ...m, lots: [], loading: false } : m))
      })
  }

  const applyBulkUnfkResponse = async (pn: string, res: BulkReverseCheckInResult) => {
    const failed = res.failed || []
    const reversed = res.reversed || []
    let msg = res.message || `Reversed ${reversed.length} lot(s).`
    if (failed.length > 0) {
      msg +=
        '\n\nFailed:\n' +
        failed.map((f) => `${f.lot_number != null ? f.lot_number : `Lot #${f.lot_id}`}: ${f.error}`).join('\n')
    }
    alert(msg)
    await loadPOs()
    if (selectedPO?.po_number === pn) {
      try {
        const updated = await getPurchaseOrder(selectedPO.id)
        setSelectedPO(updated)
        await refreshPoReceiptLots()
      } catch {
        /* ignore */
      }
    }
    try {
      const data = await getLotsByPurchaseOrder(pn)
      const arr = Array.isArray(data) ? data : []
      setUnfkModal((m) => {
        if (!m || m.po.po_number !== pn) return m
        if (!arr.some(lotEligibleForUnfk)) return null
        return { ...m, lots: arr, loading: false }
      })
    } catch {
      setUnfkModal((m) => (m && m.po.po_number === pn ? null : m))
    }
  }

  const handleBulkUnfkSelected = async () => {
    if (!unfkModal || unfkModal.loading) return
    const ids = Array.from(unfkModalSelectedIds)
    if (ids.length === 0) {
      alert('Select at least one eligible lot.')
      return
    }
    if (
      !window.confirm(
        `Reverse check-in for ${ids.length} receipt lot(s) on ${unfkModal.po.po_number}?\n\n` +
          `Each lot is removed and PO received quantities rolled back. The PO stays open; ` +
          `status returns to Issued when receipts are no longer complete.`
      )
    ) {
      return
    }
    try {
      setBulkUnfkBusy(true)
      const res = await bulkReverseCheckIn({ lotIds: ids })
      await applyBulkUnfkResponse(unfkModal.po.po_number, res)
    } catch (err: unknown) {
      alert(formatApiError(err))
    } finally {
      setBulkUnfkBusy(false)
    }
  }

  const handleBulkUnfkWholePo = async () => {
    if (!unfkModal) return
    if (
      !window.confirm(
        `Reverse check-in for every receipt lot linked to ${unfkModal.po.po_number}?\n\n` +
          `Eligible lots (fully on-hand, not used elsewhere) will be reversed. ` +
          `Lots that cannot be reversed will be skipped and listed in the summary.`
      )
    ) {
      return
    }
    try {
      setBulkUnfkBusy(true)
      const res = await bulkReverseCheckIn({ poNumber: unfkModal.po.po_number })
      await applyBulkUnfkResponse(unfkModal.po.po_number, res)
    } catch (err: unknown) {
      alert(formatApiError(err))
    } finally {
      setBulkUnfkBusy(false)
    }
  }

  const handleBulkUnfkFromDetailPo = async () => {
    if (!selectedPO || selectedPO.status === 'draft') return
    const pn = selectedPO.po_number
    if (
      !window.confirm(
        `Reverse check-in for every eligible receipt lot on ${pn}?\n\n` +
          `Lots that are partially used, allocated to sales, or used in production will be skipped.`
      )
    ) {
      return
    }
    try {
      setBulkUnfkBusy(true)
      const res = await bulkReverseCheckIn({ poNumber: pn })
      await applyBulkUnfkResponse(pn, res)
    } catch (err: unknown) {
      alert(formatApiError(err))
    } finally {
      setBulkUnfkBusy(false)
    }
  }

  const performUnfkPoLot = async (lot: PoLinkedLot) => {
    if (bulkUnfkBusy) return
    if (!lotEligibleForUnfk(lot)) return
    if (
      !window.confirm(
        `Reverse check-in for lot ${lot.lot_number}?\n\n` +
          `The lot will be removed and PO received quantities rolled back. ` +
          `The purchase order stays open — status returns to Issued if receipts are no longer complete (not deleted).`
      )
    ) {
      return
    }
    try {
      setUnfkLotId(lot.id)
      await reverseCheckIn(lot.id)
      alert('Check-in reversed.')
      await loadPOs()
      if (selectedPO?.po_number && lot.po_number && selectedPO.po_number === lot.po_number) {
        const updated = await getPurchaseOrder(selectedPO.id)
        setSelectedPO(updated)
        await refreshPoReceiptLots()
      }
      const pn = lot.po_number
      if (pn) {
        const data = await getLotsByPurchaseOrder(pn)
        const arr = Array.isArray(data) ? data : []
        setUnfkModal((m) => {
          if (!m || m.po.po_number !== pn) return m
          if (!arr.some(lotEligibleForUnfk)) return null
          return { po: m.po, lots: arr, loading: false }
        })
      }
    } catch (err: unknown) {
      alert(formatApiError(err))
    } finally {
      setUnfkLotId(null)
    }
  }

  const handleUnfkPoLot = async (lot: PoLinkedLot) => {
    await performUnfkPoLot(lot)
  }

  const isLate = (expectedDate?: string, requiredDate?: string) => {
    if (!expectedDate || !requiredDate) return false
    const e = expectedDate.trim().slice(0, 10)
    const r = requiredDate.trim().slice(0, 10)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(e) || !/^\d{4}-\d{2}-\d{2}$/.test(r)) {
      return new Date(expectedDate) > new Date(requiredDate)
    }
    return e > r
  }

  /** DateTime from API (issue date). */
  const formatDateTimeField = (dateString?: string) => {
    if (!dateString) return 'N/A'
    return formatAppDate(dateString) || 'N/A'
  }

  /** Date-only fields (required / expected delivery) as YYYY-MM-DD in US Central. */
  const formatCalendarDate = (dateString?: string) => formatAppDateFromYmd(dateString)

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

  // Convert quantity based on unit display preference (used by list view)
  const convertQuantity = (quantity: number, itemUnit: string) => {
    if (itemUnit === 'ea') return formatNumber(quantity, 0)
    if (unitDisplay === 'kg' && itemUnit === 'lbs') {
      return formatNumber(quantity * 0.453592)
    } else if (unitDisplay === 'lbs' && itemUnit === 'kg') {
      return formatNumber(quantity * 2.20462)
    }
    return formatNumber(quantity)
  }

  const getDisplayUnit = (itemUnit: string) => {
    if (itemUnit === 'ea') return 'ea'
    return unitDisplay
  }

  /** Sum line quantities in the list header unit (lbs/kg), using each line's order_uom vs master UoM. */
  const calculateTotalQuantity = (po: PurchaseOrder) => {
    if (!po.items || po.items.length === 0) return 0

    let total = 0
    for (const line of po.items) {
      const qty = line.quantity_ordered || 0
      const lineUom = (line.order_uom || '').trim() || line.item?.unit_of_measure || 'lbs'

      if (lineUom === 'ea') {
        total += qty
        continue
      }
      if (unitDisplay === 'kg' && lineUom === 'lbs') {
        total += qty * 0.453592
      } else if (unitDisplay === 'lbs' && lineUom === 'kg') {
        total += qty * 2.20462
      } else {
        total += qty
      }
    }
    return total
  }

  const primaryPos = sortedPos.filter(
    (p) => p.status !== 'received' && p.status !== 'completed'
  )
  const deeperPos = sortedPos.filter(
    (p) => p.status === 'received' || p.status === 'completed'
  )

  const renderPurchaseOrderListRow = (po: PurchaseOrder) => {
    const totalQuantity = calculateTotalQuantity(po)
    const first = po.items && po.items.length > 0 ? po.items[0] : null
    const firstLineUom = first
      ? (first.order_uom || '').trim() || first.item?.unit_of_measure || 'lbs'
      : 'lbs'
    const displayUnit = firstLineUom === 'ea' ? 'ea' : getDisplayUnit(firstLineUom)
    return (
      <tr key={po.id}>
        <td className="po-number">
          <a
            href={getPurchaseOrderPdfUrl(po.id)}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#0066cc', textDecoration: 'underline', cursor: 'pointer' }}
            onClick={(e) => {
              e.preventDefault()
              window.open(getPurchaseOrderPdfUrl(po.id), '_blank')
            }}
            title="Click to view/print purchase order PDF"
          >
            {po.po_number}
          </a>
          {(po.revision_number ?? 0) > 0 && (
            <span className="revision-badge"> Rev {po.revision_number}</span>
          )}
        </td>
        <td>{po.vendor_name || `ID: ${po.vendor_id}`}</td>
        <td>{po.status !== 'draft' ? formatDateTimeField(po.order_date) : 'Not issued'}</td>
        <td>{formatCalendarDate(po.required_date)}</td>
        <td className={isLate(po.expected_delivery_date, po.required_date) ? 'late-delivery' : ''}>
          {formatCalendarDate(po.expected_delivery_date)}
        </td>
        <td>
          {formatNumber(totalQuantity)} {displayUnit}
        </td>
        <td>{po.total ? formatCurrency(po.total) : '0.00'}</td>
        <td>
          <span className={getStatusBadgeClass(po.status)}>{po.status}</span>
          {po.drop_ship && (
            <span className="po-drop-ship-badge" title="Drop ship — do not check in to inventory">
              DS
            </span>
          )}
        </td>
        <td>
          <div className="action-buttons">
            <button onClick={() => handleView(po.id)} className="btn btn-sm btn-primary">
              View
            </button>
            {po.status === 'draft' && (
              <>
                <button
                  onClick={() => handleIssue(po)}
                  className="btn btn-sm btn-success"
                  disabled={issuingPoId !== null}
                >
                  {issuingPoId === po.id ? 'Issuing…' : 'Issue'}
                </button>
                <button onClick={() => handleDelete(po.id)} className="btn btn-sm btn-danger">
                  Delete
                </button>
              </>
            )}
            {(po.status === 'issued' || po.status === 'received') && (
              <>
                <button onClick={() => handleRevise(po.id)} className="btn btn-sm btn-warning">
                  Revise
                </button>
                {user && (
                  <button
                    type="button"
                    onClick={() => openUnfkModalForPo(po)}
                    className="btn btn-sm btn-outline-danger"
                    title="Reverse a mistaken check-in (pick which receipt lots to undo)"
                    disabled={
                      bulkUnfkBusy ||
                      unfkLotId !== null ||
                      (unfkModal?.loading === true && unfkModal.po.id === po.id)
                    }
                  >
                    Reverse check-in
                  </button>
                )}
                <button onClick={() => handleCancel(po.id)} className="btn btn-sm btn-danger">
                  Cancel
                </button>
              </>
            )}
          </div>
        </td>
      </tr>
    )
  }

  const unfkPickLotModal = unfkModal ? (
    <div
      className="modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={() => {
        if (!unfkModal.loading && unfkLotId === null && !bulkUnfkBusy) setUnfkModal(null)
      }}
    >
      <div
        className="modal-content po-unfk-pick-modal"
        style={{ background: 'white', padding: '1.5rem', borderRadius: 8, maxWidth: 640, width: 'min(100%, 640px)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>Reverse check-in</h3>
        <p style={{ marginBottom: '0.75rem', color: '#4b5563', fontSize: '0.9rem' }}>
          <strong>{unfkModal.po.po_number}</strong> — select lots (or reverse all eligible receipts on this PO). The PO is not cancelled;
          status returns to Issued when receipts are no longer complete.
        </p>
        {unfkModal.loading ? (
          <p style={{ margin: '1rem 0' }}>Loading receipt lots…</p>
        ) : unfkModal.lots.length === 0 ? (
          <p style={{ margin: '1rem 0' }}>No receipt lots found for this PO.</p>
        ) : (
          (() => {
            const eligibleLots = unfkModal.lots.filter(lotEligibleForUnfk)
            const allEligibleSelected =
              eligibleLots.length > 0 && eligibleLots.every((l) => unfkModalSelectedIds.has(l.id))
            return (
          <div className="po-unfk-pick-modal-table-wrap">
            <table className="po-unfk-pick-table">
              <thead>
                <tr>
                  <th className="po-unfk-pick-th-check">
                    <input
                      type="checkbox"
                      checked={allEligibleSelected}
                      title="Select all eligible lots"
                      disabled={bulkUnfkBusy || unfkLotId !== null || eligibleLots.length === 0}
                      onChange={() => {
                        if (allEligibleSelected) {
                          setUnfkModalSelectedIds(new Set())
                        } else {
                          setUnfkModalSelectedIds(new Set(eligibleLots.map((l) => l.id)))
                        }
                      }}
                    />
                  </th>
                  <th>SKU</th>
                  <th>Lot #</th>
                  <th>Qty</th>
                  <th>On hand</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {unfkModal.lots.map((lot) => {
                  const ok = lotEligibleForUnfk(lot)
                  const iu = lot.item?.unit_of_measure || 'lbs'
                  const fmtQty = (q: number) => (iu === 'ea' ? formatNumber(q, 0) : formatNumber(q))
                  return (
                    <tr key={lot.id}>
                      <td className="po-unfk-pick-td-check">
                        {ok ? (
                          <input
                            type="checkbox"
                            checked={unfkModalSelectedIds.has(lot.id)}
                            disabled={bulkUnfkBusy || unfkLotId !== null}
                            onChange={() => {
                              setUnfkModalSelectedIds((prev) => {
                                const next = new Set(prev)
                                if (next.has(lot.id)) next.delete(lot.id)
                                else next.add(lot.id)
                                return next
                              })
                            }}
                          />
                        ) : (
                          <span className="po-unfk-pick-disabled"> </span>
                        )}
                      </td>
                      <td>{lot.item?.sku || '—'}</td>
                      <td>{lot.lot_number}</td>
                      <td>
                        {fmtQty(lot.quantity)} {iu}
                      </td>
                      <td>
                        {fmtQty(lot.quantity_remaining)} {iu}
                      </td>
                      <td>
                        {ok ? (
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            disabled={unfkLotId !== null || bulkUnfkBusy}
                            onClick={() => void performUnfkPoLot(lot)}
                          >
                            {unfkLotId === lot.id ? '…' : 'Reverse'}
                          </button>
                        ) : (
                          <span
                            className="po-unfk-pick-disabled"
                            title="Lot must be fully on-hand (not consumed, allocated, or used in production)."
                          >
                            —
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!unfkModal.lots.some(lotEligibleForUnfk) ? (
              <p className="po-unfk-pick-hint">
                None of these lots can be reversed yet — each must be fully on-hand with no downstream use.
              </p>
            ) : null}
          </div>
            )
          })()
        )}
        <div style={{ marginTop: '1rem', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {!unfkModal.loading && unfkModal.lots.length > 0 && unfkModal.lots.some(lotEligibleForUnfk) ? (
            <>
              <button
                type="button"
                className="btn btn-danger"
                disabled={
                  bulkUnfkBusy || unfkLotId !== null || unfkModalSelectedIds.size === 0
                }
                onClick={() => void handleBulkUnfkSelected()}
              >
                {bulkUnfkBusy ? 'Working…' : `Reverse selected (${unfkModalSelectedIds.size})`}
              </button>
              <button
                type="button"
                className="btn btn-outline-danger po-unfk-modal-outline"
                disabled={bulkUnfkBusy || unfkLotId !== null}
                onClick={() => void handleBulkUnfkWholePo()}
              >
                All receipts on PO
              </button>
            </>
          ) : null}
          <button
            type="button"
            className="btn btn-secondary"
            disabled={unfkLotId !== null || bulkUnfkBusy}
            onClick={() => setUnfkModal(null)}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  ) : null

  const issueDateModal = issueModalPo ? (
      <div
        className="modal-overlay"
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={() => setIssueModalPo(null)}
      >
        <div
          className="modal-content"
          style={{ background: 'white', padding: '1.5rem', borderRadius: 8, maxWidth: 420 }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 style={{ marginTop: 0 }}>Issue purchase order</h3>
          <p style={{ marginBottom: '0.75rem' }}>Choose the issue date for this PO (shown on PDF and lists). Inventory will update when you confirm.</p>
          <div className="form-group">
            <label htmlFor="po-issue-date">Issue date</label>
            <input
              id="po-issue-date"
              type="date"
              value={issueDateValue}
              onChange={(e) => setIssueDateValue(e.target.value)}
              max={maxDateForEntry}
              min={minDateForEntry}
            />
          </div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-success"
              disabled={issuingPoId !== null}
              onClick={() => void submitIssueFromModal()}
            >
              {issuingPoId === issueModalPo.id ? 'Issuing…' : 'Issue PO'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={issuingPoId !== null}
              onClick={() => setIssueModalPo(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    ) : null

  if (loading && pos.length === 0) {
    return (
      <>
        {issueDateModal}
        {unfkPickLotModal}
        <div className="loading">Loading purchase orders...</div>
      </>
    )
  }

  if (selectedPO) {
    const poItems = selectedPO.items || []
    const isDraftPo = selectedPO.status === 'draft'
    const isReceivedOrCompletedPo =
      selectedPO.status === 'received' || selectedPO.status === 'completed'
    const linesWithReceiptQty = isDraftPo
      ? []
      : poItems.filter((i) => (i.quantity_received || 0) > 0)
    /** Lines shown under Deeper: use line-level qty when present; else whole PO when status is received/completed. */
    const deeperLines =
      isDraftPo
        ? []
        : linesWithReceiptQty.length > 0
          ? linesWithReceiptQty
          : isReceivedOrCompletedPo
            ? poItems
            : []
    const openLines = isDraftPo
      ? poItems
      : isReceivedOrCompletedPo && linesWithReceiptQty.length === 0
        ? []
        : poItems.filter((i) => (i.quantity_received || 0) <= 0)
    const primaryLines = isDraftPo ? poItems : openLines
    const canUnfkReceipt = Boolean(user)

    return (
      <>
        {issueDateModal}
        {unfkPickLotModal}
        <div className="po-detail-view">
        <div className="po-detail-header">
          <h2>Purchase Order Details</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {selectedPO.status === 'draft' && (
              <button
                type="button"
                onClick={() => handleIssue(selectedPO)}
                className="btn btn-success"
                disabled={issuingPoId !== null}
              >
                {issuingPoId === selectedPO.id ? 'Issuing…' : 'Issue'}
              </button>
            )}
            <button type="button" onClick={() => setSelectedPO(null)} className="btn btn-secondary">
              ← Back to List
            </button>
          </div>
        </div>

        <div className="po-detail-content">
          <div className="po-info-section">
            <h3>PO Information</h3>
            <div className="info-grid">
              <div className="info-item info-item-editable">
                <label>PO Number:</label>
                {godModeOn && canUseGodMode && editingPoNumber ? (
                  <div className="edit-inline">
                    <input
                      type="text"
                      value={poNumberDraft}
                      onChange={(e) => setPoNumberDraft(e.target.value)}
                      style={{ minWidth: '12rem' }}
                    />
                    <button type="button" onClick={handleSavePoNumber} className="btn btn-sm btn-primary">
                      Save
                    </button>
                    <button type="button" onClick={handleCancelEditPoNumber} className="btn btn-sm btn-secondary">
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="edit-inline">
                    <span>
                      <a
                        href={getPurchaseOrderPdfUrl(selectedPO.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: '#0066cc', textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.preventDefault()
                          window.open(getPurchaseOrderPdfUrl(selectedPO.id), '_blank')
                        }}
                        title="Click to view/print purchase order PDF"
                      >
                        {selectedPO.po_number}
                      </a>
                      {(selectedPO.revision_number ?? 0) > 0 && (
                        <span className="revision-badge">Rev {selectedPO.revision_number}</span>
                      )}
                    </span>
                    {godModeOn && canUseGodMode && (
                      <button type="button" onClick={() => setEditingPoNumber(true)} className="btn btn-sm btn-secondary">
                        Edit
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="info-item">
                <label>Status:</label>
                <span className={getStatusBadgeClass(selectedPO.status)}>{selectedPO.status}</span>
              </div>
              <div className="info-item info-item-editable">
                <label>PO / Issue date:</label>
                {selectedPO.status === 'draft' &&
                godModeOn &&
                canUseGodMode &&
                editingOrderDate ? (
                  <div className="edit-inline">
                    <input
                      type="date"
                      value={orderDateDraftValue}
                      onChange={(e) => setOrderDateDraftValue(e.target.value)}
                      max={maxDateForEntry}
                      min={minDateForEntry}
                    />
                    <button type="button" onClick={handleSaveOrderDate} className="btn btn-sm btn-primary">
                      Save
                    </button>
                    <button type="button" onClick={handleCancelEditOrderDate} className="btn btn-sm btn-secondary">
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="edit-inline">
                    <span>{formatDateTimeField(selectedPO.order_date)}</span>
                    {selectedPO.status === 'draft' && godModeOn && canUseGodMode && (
                      <button type="button" onClick={() => setEditingOrderDate(true)} className="btn btn-sm btn-secondary">
                        Edit
                      </button>
                    )}
                  </div>
                )}
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
                    <span>{formatCalendarDate(selectedPO.required_date)}</span>
                    {(selectedPO.status === 'draft' || selectedPO.status === 'superseded') && (
                      <button onClick={handleEditRequiredDate} className="btn btn-sm btn-secondary">Edit</button>
                    )}
                  </div>
                )}
              </div>
              <div className="info-item">
                <label>Expected Delivery:</label>
                <span className={isLate(selectedPO.expected_delivery_date, selectedPO.required_date) ? 'late-delivery' : ''}>
                  {formatCalendarDate(selectedPO.expected_delivery_date)}
                </span>
              </div>
              <div className="info-item">
                <label>Vendor:</label>
                <span>{selectedPO.vendor_name || `ID: ${selectedPO.vendor_id}`}</span>
              </div>
              {selectedPO.total != null && (
                <div className="info-item">
                  <label>Total:</label>
                  <span>{formatCurrency(selectedPO.total)}</span>
                </div>
              )}
              {(selectedPO.discount != null && selectedPO.discount !== 0) && (
                <div className="info-item">
                  <label>Discount:</label>
                  <span>{formatCurrency(selectedPO.discount)}</span>
                </div>
              )}
              {(selectedPO.shipping_cost != null && selectedPO.shipping_cost !== 0) && (
                <div className="info-item">
                  <label>Shipping:</label>
                  <span>{formatCurrency(selectedPO.shipping_cost)}</span>
                </div>
              )}
            </div>
          </div>

          {selectedPO.status === 'draft' && (
            <div className="po-tracking-section" style={{ marginTop: '1rem' }}>
              <h3>Discount & Shipping (editable for draft)</h3>
              <div className="tracking-form">
                <div className="form-group">
                  <label>Discount ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={discountValue}
                    onChange={(e) => setDiscountValue(e.target.value)}
                    placeholder="0"
                    className="number-input"
                  />
                </div>
                <div className="form-group">
                  <label>Shipping cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={shippingCostValue}
                    onChange={(e) => setShippingCostValue(e.target.value)}
                    placeholder="0"
                    className="number-input"
                  />
                </div>
                <button onClick={handleSaveDiscountAndShipping} className="btn btn-primary" disabled={savingTotals}>
                  {savingTotals ? 'Saving...' : 'Save Discount & Shipping'}
                </button>
              </div>
            </div>
          )}

          <div className="po-items-section">
            <h3>Items</h3>
            {!isDraftPo && primaryLines.length > 0 && deeperLines.length > 0 && (
              <p className="po-items-receive-hint">
                Open lines only (nothing received yet on the line). Lines with check-ins are under{' '}
                <strong>Deeper…</strong>.
              </p>
            )}
            <table className="po-items-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Description</th>
                  <th>Unit cost</th>
                  <th>Quantity Ordered</th>
                  <th>Quantity Received</th>
                  <th>Amount</th>
                  <th>Line notes</th>
                  {selectedPO.status === 'draft' && <th />}
                </tr>
              </thead>
              <tbody>
                {!isDraftPo && primaryLines.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      All lines have receipt activity. Use <strong>Deeper…</strong> below for received lines, lots, and{' '}
                      <strong>Reverse check-in</strong>.
                    </td>
                  </tr>
                ) : (
                  primaryLines.map((item) => {
                  const displayName = formatPoLineVendorLabel(item.item, item.description)
                  const nativeUom = item.item?.unit_of_measure || 'lbs'
                  const lineUom = (item.order_uom || '').trim() || nativeUom
                  const draft = poLineDrafts[item.id]
                  const qtyForAmount =
                    selectedPO.status === 'draft' && draft
                      ? parseFloat(draft.quantity) || 0
                      : item.quantity_ordered
                  const displayUnitCost =
                    selectedPO.status === 'draft' && draft
                      ? parseFloat(draft.unit_cost) || 0
                      : item.unit_cost || 0
                  const showLbsKgToggle = nativeUom === 'lbs' || nativeUom === 'kg'
                  return (
                    <tr key={item.id}>
                      <td>{item.item?.sku || 'N/A'}</td>
                      <td>{displayName}</td>
                      <td>
                        {selectedPO.status === 'draft' && draft ? (
                          <div className="po-line-cost-edit">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              className="number-input"
                              value={draft.unit_cost}
                              onChange={(e) =>
                                setPoLineDrafts((prev) => {
                                  const cur = prev[item.id]
                                  if (!cur) return prev
                                  return { ...prev, [item.id]: { ...cur, unit_cost: e.target.value } }
                                })
                              }
                              title="Price per unit of measure shown on this line"
                            />
                            <span className="po-line-uom">{draft.order_uom}</span>
                          </div>
                        ) : item.unit_cost ? (
                          `${formatCurrency(item.unit_cost)} ${lineUom}`
                        ) : (
                          `0.00 ${lineUom}`
                        )}
                      </td>
                      <td>
                        {selectedPO.status === 'draft' && draft ? (
                          <div className="po-line-qty-edit">
                            <input
                              type="number"
                              step="any"
                              min="0"
                              className="number-input po-line-qty-input"
                              value={draft.quantity}
                              onChange={(e) =>
                                setPoLineDrafts((prev) => {
                                  const cur = prev[item.id]
                                  if (!cur) return prev
                                  return { ...prev, [item.id]: { ...cur, quantity: e.target.value } }
                                })
                              }
                            />
                            {showLbsKgToggle ? (
                              <div className="po-line-uom-toggle" role="group" aria-label="Unit of measure">
                                <button
                                  type="button"
                                  className={draft.order_uom === 'lbs' ? 'active' : ''}
                                  onClick={() => toggleDraftLineUom(item.id, 'lbs')}
                                >
                                  lbs
                                </button>
                                <button
                                  type="button"
                                  className={draft.order_uom === 'kg' ? 'active' : ''}
                                  onClick={() => toggleDraftLineUom(item.id, 'kg')}
                                >
                                  kg
                                </button>
                              </div>
                            ) : (
                              <span className="po-line-uom">{draft.order_uom}</span>
                            )}
                          </div>
                        ) : (
                          `${item.quantity_ordered} ${lineUom}`
                        )}
                      </td>
                      <td>{item.quantity_received || 0}</td>
                      <td>{formatCurrency(displayUnitCost * qtyForAmount)}</td>
                      <td>
                        {selectedPO.status === 'draft' && draft ? (
                          <input
                            type="text"
                            className="po-line-notes-input"
                            value={draft.notes}
                            onChange={(e) =>
                              setPoLineDrafts((prev) => {
                                const cur = prev[item.id]
                                if (!cur) return prev
                                return { ...prev, [item.id]: { ...cur, notes: e.target.value } }
                              })
                            }
                            placeholder="Optional"
                          />
                        ) : (
                          item.notes || ''
                        )}
                      </td>
                      {selectedPO.status === 'draft' && (
                        <td>
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            disabled={savingLineId === item.id}
                            onClick={() => handleSavePoLine(item.id)}
                          >
                            {savingLineId === item.id ? 'Saving…' : 'Save line'}
                          </button>
                        </td>
                      )}
                    </tr>
                  )
                  })
                )}
              </tbody>
            </table>
            {!isDraftPo && deeperLines.length > 0 && (
              <>
                <div className="po-deeper-controls">
                  <button
                    type="button"
                    className="po-deeper-toggle"
                    onClick={() => void togglePoItemsDeeper()}
                    title="Received lines, check-in lots, and reverse check-in (undo mistaken receipts). Full history: Logs."
                  >
                    {poItemsDeeperOpen ? 'Too deep...' : 'Deeper…'}
                  </button>
                  {poReceiptLotsLoading && <span className="po-deeper-loading"> Loading…</span>}
                </div>
                {poItemsDeeperOpen && (
                  <div className="po-deeper-section">
                    {poReceiptLots === null && poReceiptLotsLoading ? (
                      <div className="loading-lots po-deeper-loading-block">Loading receipt lots…</div>
                    ) : (
                      <>
                        <div className="po-deeper-heading-row">
                          <h4 className="po-deeper-heading">Received lines &amp; check-in lots</h4>
                          {canUnfkReceipt && (
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-danger po-unfk-modal-outline"
                              disabled={bulkUnfkBusy || unfkLotId !== null}
                              title="Reverse check-in for every eligible receipt lot on this PO"
                              onClick={() => void handleBulkUnfkFromDetailPo()}
                            >
                              {bulkUnfkBusy ? 'Working…' : 'Reverse all eligible'}
                            </button>
                          )}
                        </div>
                        <div className="po-deeper-table-wrap" role="region" aria-label="Receipt lots and reverse check-in">
                          <table className="po-items-table po-items-table-deeper">
                          <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Description</th>
                              <th>Qty ordered</th>
                              <th>Qty received (PO)</th>
                              <th>Lot #</th>
                              <th>Lot received</th>
                              <th>Available</th>
                              <th>Received</th>
                              <th>Reverse</th>
                            </tr>
                          </thead>
                          <tbody>
                            {deeperLines.flatMap((line) => {
                              const displayName = formatPoLineVendorLabel(line.item, line.description)
                              const lineUom =
                                (line.order_uom || '').trim() || line.item?.unit_of_measure || 'lbs'
                              const lots = (poReceiptLots || []).filter((l) => l.item.id === line.item.id)
                              const fmtLotQty = (q: number, uom: string) =>
                                uom === 'ea'
                                  ? `${formatNumber(q, 0)} ea`
                                  : `${convertQuantity(q, uom)} ${getDisplayUnit(uom)}`
                              if (lots.length === 0) {
                                return [
                                  <tr key={`line-${line.id}`} className="po-deeper-line-row">
                                    <td>{line.item?.sku || 'N/A'}</td>
                                    <td>{displayName}</td>
                                    <td>
                                      {line.quantity_ordered} {lineUom}
                                    </td>
                                    <td>
                                      {line.quantity_received || 0} {lineUom}
                                    </td>
                                    <td colSpan={5} className="po-deeper-missing-lots">
                                      No lots on this PO for this item (e.g. legacy check-in or different PO # on lot).
                                    </td>
                                  </tr>,
                                ]
                              }
                              return lots.map((lot) => {
                                const iu = lot.item?.unit_of_measure || 'lbs'
                                const unfkOk = lotEligibleForUnfk(lot)
                                return (
                                  <tr key={`${line.id}-${lot.id}`} className="po-deeper-lot-row">
                                    <td>{line.item?.sku || 'N/A'}</td>
                                    <td>{displayName}</td>
                                    <td>
                                      {line.quantity_ordered} {lineUom}
                                    </td>
                                    <td>
                                      {line.quantity_received || 0} {lineUom}
                                    </td>
                                    <td>{lot.lot_number}</td>
                                    <td>{fmtLotQty(lot.quantity, iu)}</td>
                                    <td>{fmtLotQty(lot.quantity_remaining, iu)}</td>
                                    <td>
                                      {lot.received_date
                                        ? formatAppDate(lot.received_date)
                                        : '—'}
                                    </td>
                                    <td>
                                      {canUnfkReceipt ? (
                                        <button
                                          type="button"
                                          className="btn btn-sm btn-danger"
                                          disabled={!unfkOk || unfkLotId !== null || bulkUnfkBusy}
                                          title={
                                            unfkOk
                                              ? 'Reverse this check-in (removes lot, rolls back PO received when possible)'
                                              : 'Only full unused receipts can be reversed (not consumed, allocated, or used in production).'
                                          }
                                          onClick={() => void handleUnfkPoLot(lot)}
                                        >
                                          {unfkLotId === lot.id ? '…' : 'Reverse'}
                                        </button>
                                      ) : (
                                        <span className="po-unfk-staff-only" title="Log in to reverse a check-in.">
                                          —
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                )
                              })
                            })}
                          </tbody>
                        </table>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </>
            )}
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

          {selectedPO.status === 'draft' ? (
            <div className="po-notify-party-section">
              <h3>Notify party (editable for draft)</h3>
              <div className="notify-party-edit-hint">
                Optional: select one or more contacts that handle importation (e.g. customs broker by port).
              </div>

              {notifyPartyContactIdsDraft.length > 0 && (
                <div className="notify-party-selected-contacts">
                  <h4>Selected contacts</h4>
                  {notifyPartyContactIdsDraft.map((id) => {
                    const c = notifyPartyContactsCache[id]
                    if (!c) return null
                    return (
                      <div key={id} className="notify-party-selected-item">
                        <div className="notify-party-selected-item-main">
                          <strong>
                            {c.vendor_name || c.vendor?.name || 'Notify party'}
                            {c.location_label ? ` — ${c.location_label}` : ''}
                          </strong>
                          <div>{c.name}</div>
                          {(c.emails || []).map((addr) => (
                            <div key={addr}>{addr}</div>
                          ))}
                          {c.phone && <div>{c.phone}</div>}
                          {c.notes && <div className="notify-party-notes">Notes: {c.notes}</div>}
                        </div>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => toggleNotifyPartyContact(id)}>
                          Remove
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}

              <div className="notify-party-edit-row">
                <div className="form-group">
                  <label>Service vendor</label>
                  <select
                    value={notifyPartyAddVendorId}
                    onChange={(e) => {
                      const val = e.target.value
                      setNotifyPartyAddVendorId(val)
                      if (!val) {
                        setNotifyPartyAddContacts([])
                        return
                      }
                      loadNotifyPartyContacts(parseInt(val, 10))
                    }}
                  >
                    <option value="">— Add contacts —</option>
                    {serviceVendors.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {notifyPartyAddVendorId && (
                <div className="notify-party-edit-contacts">
                  <h4>Contacts</h4>
                  {notifyPartyContactsLoading ? (
                    <div className="form-hint">Loading contacts...</div>
                  ) : notifyPartyAddContacts.length === 0 ? (
                    <div className="form-hint">No contacts found for this service vendor.</div>
                  ) : (
                    <div className="notify-party-checkboxes">
                      {notifyPartyAddContacts.map((c) => {
                        const checked = notifyPartyContactIdsDraft.includes(c.id)
                        return (
                          <label key={c.id} className="notify-party-checkbox">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleNotifyPartyContact(c.id)}
                            />
                            <span>
                              {c.name}
                              {c.location_label ? ` — ${c.location_label}` : ''}
                              {(c.emails || []).length > 0 && (
                                <div className="notify-party-emails">{c.emails!.join(', ')}</div>
                              )}
                              {c.notes && <div className="notify-party-notes">Notes: {c.notes}</div>}
                            </span>
                          </label>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              <div className="notify-party-save-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleSaveNotifyParties}
                  disabled={savingNotifyParties}
                >
                  {savingNotifyParties ? 'Saving...' : 'Save Notify Party Contacts'}
                </button>
              </div>
            </div>
          ) : (
            selectedPO.notify_party_contacts &&
            selectedPO.notify_party_contacts.length > 0 && (
              <div className="po-notify-party-section">
                <h3>Notify party</h3>
                {selectedPO.notify_party_contacts.map((c) => (
                  <p key={c.id}>
                    <strong>
                      {c.vendor_name || c.vendor?.name || 'Notify party'}
                      {c.location_label ? ` — ${c.location_label}` : ''}
                    </strong>
                    <br />
                    {c.name}
                    {(c.emails || []).map((addr) => (
                      <span key={addr}>
                        <br />
                        {addr}
                      </span>
                    ))}
                    {c.phone && (
                      <>
                        <br />
                        {c.phone}
                      </>
                    )}
                    {c.notes && (
                      <>
                        <br />
                        <em>Notes: {c.notes}</em>
                      </>
                    )}
                  </p>
                ))}
              </div>
            )
          )}

          {selectedPO.status === 'draft' ? (
            <div className="po-notes-section">
              <h3>PO comments / notes</h3>
              <textarea
                className="po-comments-textarea"
                rows={4}
                value={poNotesDraft}
                onChange={(e) => setPoNotesDraft(e.target.value)}
                placeholder="Internal comments, special terms, or instructions for this PO"
              />
              <button
                type="button"
                className="btn btn-primary"
                disabled={savingPoNotes}
                onClick={handleSavePoNotes}
              >
                {savingPoNotes ? 'Saving…' : 'Save comments'}
              </button>
            </div>
          ) : (
            selectedPO.notes && (
              <div className="po-notes-section">
                <h3>PO comments / notes</h3>
                <p>{selectedPO.notes}</p>
              </div>
            )
          )}
        </div>
      </div>
      </>
    )
  }

  return (
    <>
      {issueDateModal}
      {unfkPickLotModal}
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
        <>
          <p className="po-list-open-hint">
            Open list: draft, issued, cancelled, superseded, and other non-closed POs. Received &amp; completed are
            under <strong>Deeper…</strong>.
          </p>
          <table className="po-table po-table-primary-list">
            <thead>
              <tr>
                <th className="sortable" onClick={() => handleSort('po_number')}>
                  PO Number {sort.key === 'po_number' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="sortable" onClick={() => handleSort('vendor')}>
                  Vendor {sort.key === 'vendor' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="sortable" onClick={() => handleSort('order_date')}>
                  Issue Date {sort.key === 'order_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="sortable" onClick={() => handleSort('required_date')}>
                  Required Date {sort.key === 'required_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="sortable" onClick={() => handleSort('expected_delivery_date')}>
                  Expected Delivery {sort.key === 'expected_delivery_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th>Quantity</th>
                <th className="sortable" onClick={() => handleSort('total')}>
                  Total {sort.key === 'total' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="sortable" onClick={() => handleSort('status')}>
                  Status {sort.key === 'status' && (sort.dir === 'asc' ? '↑' : '↓')}
                </th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {primaryPos.length === 0 && deeperPos.length > 0 ? (
                <tr>
                  <td colSpan={9} className="po-list-deeper-prompt">
                    Every PO in this view is <strong>received</strong> or <strong>completed</strong>. Click{' '}
                    <strong>Deeper…</strong> below to see them.
                  </td>
                </tr>
              ) : primaryPos.length === 0 ? (
                <tr>
                  <td colSpan={9}>No purchase orders match this filter.</td>
                </tr>
              ) : (
                primaryPos.map(renderPurchaseOrderListRow)
              )}
            </tbody>
          </table>
          {deeperPos.length > 0 && (
            <>
              <div className="po-list-deeper-controls">
                <button
                  type="button"
                  className="po-deeper-toggle"
                  onClick={() => setPoListDeeperOpen((o) => !o)}
                  title="Purchase orders in received or completed status."
                >
                  {poListDeeperOpen ? 'Too deep...' : 'Deeper…'}
                </button>
                <span className="po-deeper-count">{deeperPos.length} received/completed</span>
              </div>
              {poListDeeperOpen && (
                <table className="po-table po-table-deeper-list">
                  <thead>
                    <tr>
                      <th className="sortable" onClick={() => handleSort('po_number')}>
                        PO Number {sort.key === 'po_number' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="sortable" onClick={() => handleSort('vendor')}>
                        Vendor {sort.key === 'vendor' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="sortable" onClick={() => handleSort('order_date')}>
                        Issue Date {sort.key === 'order_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="sortable" onClick={() => handleSort('required_date')}>
                        Required Date {sort.key === 'required_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="sortable" onClick={() => handleSort('expected_delivery_date')}>
                        Expected Delivery {sort.key === 'expected_delivery_date' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th>Quantity</th>
                      <th className="sortable" onClick={() => handleSort('total')}>
                        Total {sort.key === 'total' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th className="sortable" onClick={() => handleSort('status')}>
                        Status {sort.key === 'status' && (sort.dir === 'asc' ? '↑' : '↓')}
                      </th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>{deeperPos.map(renderPurchaseOrderListRow)}</tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
    </div>
    </>
  )
}

export default PurchaseOrderList


