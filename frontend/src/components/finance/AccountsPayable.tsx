import React, { useState, useEffect } from 'react'
import {
  getAccountsPayable,
  getAccountsPayableAging,
  updateAccountsPayableEntry,
  getApPoWorkqueue,
  createAccountsPayableForPo,
  type ApPoWorkqueueRow,
  type AccountsPayableLine,
  type CreateApForPoPayload,
} from '../../api/finance'
import PaymentEntry from './PaymentEntry'
import { formatAppDate } from '../../utils/appDateFormat'
import './AccountsPayable.css'

type EditingEntry = AccountsPayableLine

const AccountsPayable: React.FC = () => {
  const [poRows, setPoRows] = useState<ApPoWorkqueueRow[]>([])
  const [standaloneEntries, setStandaloneEntries] = useState<AccountsPayableLine[]>([])
  const [agingReport, setAgingReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [showAging, setShowAging] = useState(false)
  const [showPaymentEntry, setShowPaymentEntry] = useState(false)
  const [editingEntry, setEditingEntry] = useState<EditingEntry | null>(null)
  const [selectedApEntryId, setSelectedApEntryId] = useState<number | null>(null)
  const [poDetail, setPoDetail] = useState<ApPoWorkqueueRow | null>(null)
  const [addBillSaving, setAddBillSaving] = useState(false)
  const [addBillForm, setAddBillForm] = useState({
    cost_category: 'material' as '' | 'material' | 'freight' | 'duty_tax',
    invoice_number: '',
    invoice_date: '',
    due_date: '',
    original_amount: '',
    freight_total: '',
    tariff_duties_paid: '',
    shipment_method: '' as '' | 'air' | 'sea',
    notes: '',
  })
  const [filters, setFilters] = useState({
    status: '',
    vendor_name: '',
    workflow: '',
  })

  useEffect(() => {
    loadData()
  }, [filters.status, filters.vendor_name, filters.workflow])

  const resetAddBillForm = () => {
    const today = new Date().toISOString().slice(0, 10)
    setAddBillForm({
      cost_category: 'material',
      invoice_number: '',
      invoice_date: today,
      due_date: '',
      original_amount: '',
      freight_total: '',
      tariff_duties_paid: '',
      shipment_method: '',
      notes: '',
    })
  }

  const loadData = async () => {
    try {
      setLoading(true)
      const vendor = filters.vendor_name.trim() || undefined
      const workflow = filters.workflow.trim() || undefined
      const [wq, st] = await Promise.all([
        getApPoWorkqueue({ vendor_name: vendor, workflow }),
        getAccountsPayable({
          status: filters.status || undefined,
          vendor_name: vendor,
          standalone_only: true,
        }),
      ])
      setPoRows(Array.isArray(wq) ? wq : [])
      setStandaloneEntries(Array.isArray(st) ? st : [])
    } catch (error) {
      console.error('Failed to load AP data:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadAgingReport = async () => {
    try {
      const data = await getAccountsPayableAging()
      setAgingReport(data)
      setShowAging(true)
    } catch (error) {
      console.error('Failed to load aging report:', error)
    }
  }

  const getStatusBadgeClass = (s: string) => {
    switch (s) {
      case 'paid':
        return 'status-paid'
      case 'partial':
        return 'status-partial'
      case 'overdue':
        return 'status-overdue'
      case 'open':
        return 'status-open'
      default:
        return 'status-default'
    }
  }

  const getWorkflowBadgeClass = (wf: string) => {
    switch (wf) {
      case 'paid':
        return 'ap-wf-paid'
      case 'partial':
        return 'ap-wf-partial'
      case 'overdue':
        return 'ap-wf-overdue'
      case 'awaiting_bills':
        return 'ap-wf-awaiting'
      case 'open':
      default:
        return 'ap-wf-open'
    }
  }

  const getAgingBucketClass = (bucket: string) => {
    switch (bucket) {
      case 'over_90':
        return 'aging-over-90'
      case '61-90':
        return 'aging-61-90'
      case '31-60':
        return 'aging-31-60'
      case '0-30':
        return 'aging-0-30'
      default:
        return 'aging-not-due'
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
  }

  const formatDate = (dateString: string) => formatAppDate(dateString)

  /** Compare calendar dates; works for ISO date strings from the API. */
  const isPastDueDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return false
    const a = String(dateStr).slice(0, 10)
    const b = new Date().toISOString().slice(0, 10)
    return a < b
  }

  const openPoDetail = (row: ApPoWorkqueueRow) => {
    setPoDetail(row)
    resetAddBillForm()
  }

  const openEdit = (entry: AccountsPayableLine) => {
    setEditingEntry({ ...entry })
  }

  const handleEditSave = async () => {
    if (!editingEntry) return
    try {
      const ft = editingEntry.freight_total
      const td = editingEntry.tariff_duties_paid
      await updateAccountsPayableEntry(editingEntry.id, {
        invoice_number: editingEntry.invoice_number || null,
        invoice_date: editingEntry.invoice_date,
        cost_category: editingEntry.cost_category ?? '',
        freight_total: ft != null && ft !== ('' as any) ? Number(ft) : null,
        tariff_duties_paid: td != null && td !== ('' as any) ? Number(td) : null,
        shipment_method: editingEntry.shipment_method || null,
        notes: editingEntry.notes || null,
      })
      setEditingEntry(null)
      loadData()
      if (poDetail) {
        const wq = await getApPoWorkqueue({
          vendor_name: filters.vendor_name.trim() || undefined,
          workflow: filters.workflow.trim() || undefined,
        })
        const next = (Array.isArray(wq) ? wq : []).find((r) => r.purchase_order_id === poDetail.purchase_order_id)
        if (next) setPoDetail(next)
      }
    } catch (e) {
      console.error('Failed to update AP entry', e)
      alert('Failed to update entry. Check console.')
    }
  }

  const handleAddBillForPo = async () => {
    if (!poDetail) return
    const amt = parseFloat(String(addBillForm.original_amount))
    if (!Number.isFinite(amt) || amt < 0) {
      alert('Enter a valid original amount.')
      return
    }
    try {
      setAddBillSaving(true)
      const payload: CreateApForPoPayload = {
        purchase_order: poDetail.purchase_order_id,
        cost_category: addBillForm.cost_category,
        original_amount: amt,
        invoice_number: addBillForm.invoice_number.trim() || null,
        invoice_date: addBillForm.invoice_date || undefined,
        ...(addBillForm.due_date.trim() ? { due_date: addBillForm.due_date.trim() } : {}),
        freight_total:
          addBillForm.freight_total === ''
            ? null
            : Number.isFinite(parseFloat(addBillForm.freight_total))
              ? parseFloat(addBillForm.freight_total)
              : null,
        tariff_duties_paid:
          addBillForm.tariff_duties_paid === ''
            ? null
            : Number.isFinite(parseFloat(addBillForm.tariff_duties_paid))
              ? parseFloat(addBillForm.tariff_duties_paid)
              : null,
        shipment_method: addBillForm.shipment_method || null,
        notes: addBillForm.notes.trim() || null,
      }
      await createAccountsPayableForPo(payload)
      resetAddBillForm()
      await loadData()
      const wq = await getApPoWorkqueue({
        vendor_name: filters.vendor_name.trim() || undefined,
        workflow: filters.workflow.trim() || undefined,
      })
      const next = (Array.isArray(wq) ? wq : []).find((r) => r.purchase_order_id === poDetail.purchase_order_id)
      if (next) setPoDetail(next)
    } catch (e) {
      console.error('Failed to create AP line', e)
      alert('Failed to add bill. Check console.')
    } finally {
      setAddBillSaving(false)
    }
  }

  const renderApLineActions = (entry: AccountsPayableLine) => (
    <div className="ap-line-actions">
      <button type="button" className="btn-edit-ap" onClick={() => openEdit(entry)} title="Edit">
        Edit
      </button>
      {entry.balance > 0 && (
        <button
          type="button"
          className="btn-pay"
          onClick={() => {
            setSelectedApEntryId(entry.id)
            setShowPaymentEntry(true)
          }}
          title="Record Payment"
        >
          Pay
        </button>
      )}
    </div>
  )

  const renderEntryMiniRow = (entry: AccountsPayableLine) => (
    <div key={entry.id} className="ap-line-mini">
      <div className="ap-line-mini-main">
        <span className="ap-line-inv">{entry.invoice_number || '—'}</span>
        <span className="ap-line-amt">{formatCurrency(entry.original_amount)}</span>
        <span className="ap-line-bal">Bal {formatCurrency(entry.balance)}</span>
        <span
          className={`ap-line-due ${entry.balance > 0 && isPastDueDate(entry.due_date) ? 'ap-line-due-overdue' : ''}`}
          title="Due date"
        >
          Due {entry.due_date ? formatDate(entry.due_date) : '—'}
        </span>
        <span className={`status-badge ${getStatusBadgeClass(entry.status)}`}>{entry.status}</span>
      </div>
      {renderApLineActions(entry)}
    </div>
  )

  const workflowLabel = (wf: string) => {
    switch (wf) {
      case 'awaiting_bills':
        return 'Awaiting bills'
      case 'open':
        return 'Open'
      case 'partial':
        return 'Partial pay'
      case 'paid':
        return 'Paid'
      case 'overdue':
        return 'Overdue'
      default:
        return wf
    }
  }

  const poTotalOpen = poRows.reduce((s, r) => s + r.total_open_balance, 0)

  return (
    <div className="accounts-payable">
      <div className="ap-header">
        <h2>Accounts Payable</h2>
        <div className="ap-actions">
          <button type="button" onClick={loadAgingReport} className="btn btn-secondary">
            View Aging Report
          </button>
          <button
            type="button"
            onClick={() => {
              setSelectedApEntryId(null)
              setShowPaymentEntry(true)
            }}
            className="btn btn-primary"
          >
            Record payment (no PO)
          </button>
        </div>
      </div>

      <p className="ap-lede">
        <strong>Purchase orders</strong> appear here once issued (vendor POs). Open a row to record vendor, freight, and
        duty bills separately for landed cost. <strong>Due dates</strong> use the vendor&apos;s payment terms from
        Quality → Vendor (e.g. Net 30) when you leave due date blank on a new bill. Use{' '}
        <strong>Record payment (no PO)</strong> for utilities, rent, or other payables not tied to a PO.
      </p>

      <div className="ap-filters">
        <select
          value={filters.workflow}
          onChange={(e) => setFilters({ ...filters, workflow: e.target.value })}
          className="filter-select"
          title="Filter PO workbench by payment roll-up"
        >
          <option value="">All PO payment stages</option>
          <option value="awaiting_bills">Awaiting bills</option>
          <option value="open">Open</option>
          <option value="partial">Partial pay</option>
          <option value="overdue">Overdue</option>
          <option value="paid">Paid</option>
        </select>
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="filter-select"
          title="Applies to &quot;Other payables&quot; table only"
        >
          <option value="">All AP statuses (other payables)</option>
          <option value="open">Open</option>
          <option value="partial">Partial</option>
          <option value="paid">Paid</option>
          <option value="overdue">Overdue</option>
        </select>
        <input
          type="text"
          placeholder="Filter by vendor name…"
          value={filters.vendor_name}
          onChange={(e) => setFilters({ ...filters, vendor_name: e.target.value })}
          className="filter-input"
        />
      </div>

      {showAging && agingReport && (
        <div className="aging-report">
          <div className="aging-header">
            <h3>AP Aging Report - As of {formatDate(agingReport.as_of_date)}</h3>
            <button type="button" onClick={() => setShowAging(false)} className="btn-close">
              ×
            </button>
          </div>
          <div className="aging-buckets">
            {Object.entries(agingReport.aging_data).map(([bucket, entries]: [string, any]) => (
              <div key={bucket} className={`aging-bucket ${getAgingBucketClass(bucket)}`}>
                <h4>{bucket === 'not_due' ? 'Not Due' : bucket === 'over_90' ? 'Over 90 Days' : `${bucket} Days`}</h4>
                <div className="bucket-total">{formatCurrency(agingReport.totals[bucket])}</div>
                <div className="bucket-count">{entries.length} entries</div>
              </div>
            ))}
          </div>
          <div className="aging-total">
            <strong>Total Outstanding: {formatCurrency(agingReport.totals.total)}</strong>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : (
        <>
          <h3 className="ap-section-title">By purchase order</h3>
          <div className="ap-table-container">
            <table className="ap-table ap-table-po">
              <thead>
                <tr>
                  <th>PO #</th>
                  <th>Vendor</th>
                  <th>Terms</th>
                  <th>PO status</th>
                  <th>Payment stage</th>
                  <th>Next due</th>
                  <th>Order date</th>
                  <th>AP lines</th>
                  <th>Open balance</th>
                </tr>
              </thead>
              <tbody>
                {poRows.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="empty-state">
                      No issued vendor purchase orders match filters.
                    </td>
                  </tr>
                ) : (
                  poRows.map((row) => (
                    <tr
                      key={row.purchase_order_id}
                      className="ap-po-row-clickable"
                      onClick={() => openPoDetail(row)}
                      title="Open bills for this PO"
                    >
                      <td className="ap-po-num">{row.po_number}</td>
                      <td>{row.vendor_name}</td>
                      <td className="ap-terms-cell" title="Vendor profile payment terms">
                        {row.vendor_payment_terms?.trim() ? row.vendor_payment_terms : '—'}
                      </td>
                      <td>
                        <span className="ap-po-status">{row.po_status}</span>
                      </td>
                      <td>
                        <span className={`ap-workflow-badge ${getWorkflowBadgeClass(row.payment_workflow)}`}>
                          {workflowLabel(row.payment_workflow)}
                        </span>
                      </td>
                      <td
                        className={
                          row.next_open_due_date && isPastDueDate(row.next_open_due_date)
                            ? 'ap-next-due ap-next-due-overdue'
                            : 'ap-next-due'
                        }
                        title="Earliest due date among open AP lines"
                      >
                        {row.next_open_due_date ? formatDate(row.next_open_due_date) : '—'}
                      </td>
                      <td>{row.order_date ? formatDate(row.order_date) : '—'}</td>
                      <td>{row.ap_line_count}</td>
                      <td className="amount balance">{formatCurrency(row.total_open_balance)}</td>
                    </tr>
                  ))
                )}
              </tbody>
              {poRows.length > 0 && (
                <tfoot>
                  <tr className="totals-row">
                    <td colSpan={8}>
                      <strong>Total open (PO-linked)</strong>
                    </td>
                    <td className="amount balance">
                      <strong>{formatCurrency(poTotalOpen)}</strong>
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          <h3 className="ap-section-title">Other payables (no PO)</h3>
          <div className="ap-table-container">
            <table className="ap-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Invoice #</th>
                  <th>Invoice date</th>
                  <th>Due date</th>
                  <th>Original</th>
                  <th>Paid</th>
                  <th>Balance</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {standaloneEntries.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="empty-state">
                      No standalone AP entries. Use Record payment (no PO) or create entries without a PO elsewhere.
                    </td>
                  </tr>
                ) : (
                  standaloneEntries.map((entry) => (
                    <tr key={entry.id}>
                      <td>{entry.vendor_name}</td>
                      <td>{entry.invoice_number || '—'}</td>
                      <td>{formatDate(entry.invoice_date)}</td>
                      <td
                        className={
                          entry.balance > 0 && isPastDueDate(entry.due_date)
                            ? 'ap-standalone-due-overdue'
                            : ''
                        }
                      >
                        {formatDate(entry.due_date)}
                      </td>
                      <td className="amount">{formatCurrency(entry.original_amount)}</td>
                      <td className="amount">{formatCurrency(entry.amount_paid)}</td>
                      <td className="amount balance">{formatCurrency(entry.balance)}</td>
                      <td>
                        <span className={`status-badge ${getStatusBadgeClass(entry.status)}`}>{entry.status}</span>
                      </td>
                      <td>
                        <div className="ap-row-actions">
                          <button type="button" onClick={() => openEdit(entry)} className="btn-edit-ap">
                            Edit
                          </button>
                          {entry.balance > 0 && (
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedApEntryId(entry.id)
                                setShowPaymentEntry(true)
                              }}
                              className="btn-pay"
                            >
                              Pay
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              {standaloneEntries.length > 0 && (
                <tfoot>
                  <tr className="totals-row">
                    <td colSpan={4}>
                      <strong>Totals</strong>
                    </td>
                    <td className="amount">
                      <strong>
                        {formatCurrency(standaloneEntries.reduce((sum, e) => sum + e.original_amount, 0))}
                      </strong>
                    </td>
                    <td className="amount">
                      <strong>
                        {formatCurrency(standaloneEntries.reduce((sum, e) => sum + e.amount_paid, 0))}
                      </strong>
                    </td>
                    <td className="amount balance">
                      <strong>
                        {formatCurrency(standaloneEntries.reduce((sum, e) => sum + e.balance, 0))}
                      </strong>
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </>
      )}

      {poDetail && (
        <div
          className="ap-po-modal-overlay"
          onClick={() => {
            setPoDetail(null)
          }}
        >
          <div className="ap-po-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ap-po-modal-head">
              <div>
                <h3>PO {poDetail.po_number}</h3>
                <p className="ap-po-modal-sub">
                  {poDetail.vendor_name} · PO {poDetail.po_status} ·{' '}
                  <span className={`ap-workflow-badge ${getWorkflowBadgeClass(poDetail.payment_workflow)}`}>
                    {workflowLabel(poDetail.payment_workflow)}
                  </span>
                  {poDetail.vendor_payment_terms?.trim() ? (
                    <span className="ap-po-modal-terms"> · Terms: {poDetail.vendor_payment_terms}</span>
                  ) : null}
                  {poDetail.next_open_due_date ? (
                    <span
                      className={
                        isPastDueDate(poDetail.next_open_due_date)
                          ? 'ap-po-modal-next-due ap-po-modal-next-due-overdue'
                          : 'ap-po-modal-next-due'
                      }
                    >
                      {' '}
                      · Next due: {formatDate(poDetail.next_open_due_date)}
                    </span>
                  ) : null}
                </p>
              </div>
              <button type="button" className="btn-close" onClick={() => setPoDetail(null)} aria-label="Close">
                ×
              </button>
            </div>

            <p className="ap-po-modal-hint">
              Record each bill as its own line (vendor invoice = material, carrier = freight, CBP/broker = duty). Landed
              costing uses these categories on the same PO.
            </p>

            <div className="ap-po-categories">
              <div className="ap-po-cat">
                <h4>Material</h4>
                <div className="ap-po-cat-body">
                  {poDetail.material_entries.length === 0 ? (
                    <p className="ap-po-empty">No vendor invoice yet.</p>
                  ) : (
                    poDetail.material_entries.map(renderEntryMiniRow)
                  )}
                </div>
              </div>
              <div className="ap-po-cat">
                <h4>Freight</h4>
                <div className="ap-po-cat-body">
                  {poDetail.freight_entries.length === 0 ? (
                    <p className="ap-po-empty">No freight bills yet.</p>
                  ) : (
                    poDetail.freight_entries.map(renderEntryMiniRow)
                  )}
                </div>
              </div>
              <div className="ap-po-cat">
                <h4>Duty &amp; tax</h4>
                <div className="ap-po-cat-body">
                  {poDetail.duty_tax_entries.length === 0 ? (
                    <p className="ap-po-empty">No duty or broker bills yet.</p>
                  ) : (
                    poDetail.duty_tax_entries.map(renderEntryMiniRow)
                  )}
                </div>
              </div>
            </div>

            <div className="ap-add-bill">
              <h4>Add bill for this PO</h4>
              <div className="ap-add-bill-grid">
                <label>
                  Category
                  <select
                    value={addBillForm.cost_category}
                    onChange={(e) =>
                      setAddBillForm({
                        ...addBillForm,
                        cost_category: e.target.value as typeof addBillForm.cost_category,
                      })
                    }
                  >
                    <option value="material">Material (vendor invoice)</option>
                    <option value="freight">Freight</option>
                    <option value="duty_tax">Duty &amp; tax</option>
                  </select>
                </label>
                <label>
                  Invoice #
                  <input
                    type="text"
                    value={addBillForm.invoice_number}
                    onChange={(e) => setAddBillForm({ ...addBillForm, invoice_number: e.target.value })}
                    placeholder="Vendor or carrier invoice #"
                  />
                </label>
                <label>
                  Invoice date
                  <input
                    type="date"
                    value={addBillForm.invoice_date}
                    onChange={(e) => setAddBillForm({ ...addBillForm, invoice_date: e.target.value })}
                  />
                </label>
                <label>
                  Due date <span className="ap-optional">(optional)</span>
                  <input
                    type="date"
                    value={addBillForm.due_date}
                    onChange={(e) => setAddBillForm({ ...addBillForm, due_date: e.target.value })}
                    placeholder=""
                    title="Leave blank to set due date from vendor payment terms (e.g. invoice + Net 30)"
                  />
                </label>
                <label>
                  Amount (USD)
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={addBillForm.original_amount}
                    onChange={(e) => setAddBillForm({ ...addBillForm, original_amount: e.target.value })}
                    placeholder="0.00"
                  />
                </label>
                <label>
                  Freight ($) <span className="ap-optional">optional</span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={addBillForm.freight_total}
                    onChange={(e) => setAddBillForm({ ...addBillForm, freight_total: e.target.value })}
                  />
                </label>
                <label>
                  Tariff / duties ($) <span className="ap-optional">optional</span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={addBillForm.tariff_duties_paid}
                    onChange={(e) => setAddBillForm({ ...addBillForm, tariff_duties_paid: e.target.value })}
                  />
                </label>
                <label>
                  Ship method <span className="ap-optional">optional</span>
                  <select
                    value={addBillForm.shipment_method}
                    onChange={(e) =>
                      setAddBillForm({
                        ...addBillForm,
                        shipment_method: e.target.value as typeof addBillForm.shipment_method,
                      })
                    }
                  >
                    <option value="">—</option>
                    <option value="sea">Sea</option>
                    <option value="air">Air</option>
                  </select>
                </label>
                <label className="ap-add-bill-notes">
                  Notes
                  <input
                    type="text"
                    value={addBillForm.notes}
                    onChange={(e) => setAddBillForm({ ...addBillForm, notes: e.target.value })}
                  />
                </label>
              </div>
              <div className="ap-add-bill-actions">
                <button type="button" className="btn btn-primary" disabled={addBillSaving} onClick={handleAddBillForPo}>
                  {addBillSaving ? 'Saving…' : 'Add bill'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {editingEntry && (
        <div className="ap-edit-modal-overlay" onClick={() => setEditingEntry(null)}>
          <div className="ap-edit-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Edit invoice &amp; actual cost</h3>
            <p className="ap-edit-vendor">
              {editingEntry.vendor_name} {editingEntry.po_number && ` · PO ${editingEntry.po_number}`}
            </p>
            <div className="ap-edit-form">
              <label>Invoice #</label>
              <input
                type="text"
                value={editingEntry.invoice_number || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, invoice_number: e.target.value })}
                placeholder="Vendor invoice number"
              />
              <label>Invoice date</label>
              <input
                type="date"
                value={(editingEntry.invoice_date || '').toString().slice(0, 10)}
                onChange={(e) => setEditingEntry({ ...editingEntry, invoice_date: e.target.value })}
              />
              <label>Cost category (landed cost)</label>
              <select
                value={editingEntry.cost_category ?? ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, cost_category: e.target.value })}
                title="Classify this bill for raw material lot costing: separate lines per PO for vendor goods, freight, and duty."
              >
                <option value="">Legacy / unspecified (invoice total = material; use freight/duty columns as needed)</option>
                <option value="material">Material — vendor goods (COGS)</option>
                <option value="freight">Freight — logistics / carrier</option>
                <option value="duty_tax">Duty &amp; tax — CBP, customs, broker</option>
              </select>
              <label>Freight total ($)</label>
              <input
                type="number"
                step="0.01"
                min={0}
                value={editingEntry.freight_total ?? ''}
                onChange={(e) =>
                  setEditingEntry({
                    ...editingEntry,
                    freight_total: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
                placeholder="Actual total freight"
              />
              <label>Tariff / duties paid ($)</label>
              <input
                type="number"
                step="0.01"
                min={0}
                value={editingEntry.tariff_duties_paid ?? ''}
                onChange={(e) =>
                  setEditingEntry({
                    ...editingEntry,
                    tariff_duties_paid: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
                placeholder="Duties at import"
              />
              <label>Shipment method</label>
              <select
                value={editingEntry.shipment_method || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, shipment_method: e.target.value || null })}
              >
                <option value="">—</option>
                <option value="sea">Sea</option>
                <option value="air">Air</option>
              </select>
              <label>Notes</label>
              <input
                type="text"
                value={editingEntry.notes || ''}
                onChange={(e) => setEditingEntry({ ...editingEntry, notes: e.target.value })}
                placeholder="Optional notes"
              />
            </div>
            <div className="ap-edit-actions">
              <button type="button" onClick={() => setEditingEntry(null)} className="btn btn-secondary">
                Cancel
              </button>
              <button type="button" onClick={handleEditSave} className="btn btn-primary">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {showPaymentEntry && (
        <PaymentEntry
          onClose={() => {
            setShowPaymentEntry(false)
            setSelectedApEntryId(null)
          }}
          onSuccess={() => {
            loadData()
            setShowPaymentEntry(false)
            setSelectedApEntryId(null)
            if (poDetail) {
              getApPoWorkqueue({
                vendor_name: filters.vendor_name.trim() || undefined,
                workflow: filters.workflow.trim() || undefined,
              }).then((wq) => {
                const next = (Array.isArray(wq) ? wq : []).find((r) => r.purchase_order_id === poDetail.purchase_order_id)
                if (next) setPoDetail(next)
              })
            }
          }}
          paymentType="ap_payment"
          apEntryId={selectedApEntryId || undefined}
        />
      )}
    </div>
  )
}

export default AccountsPayable
