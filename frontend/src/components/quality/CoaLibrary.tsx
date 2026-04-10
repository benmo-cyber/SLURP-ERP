import { useState, useEffect } from 'react'
import {
  getLotCoaCertificates,
  getLotCoaCustomerCopies,
  type LotCoaCertificateRow,
  type LotCoaCustomerCopyRow,
} from '../../api/coa'
import { formatAppDateTimeShort } from '../../utils/appDateFormat'
import './CoaLibrary.css'

type Tab = 'master' | 'customer'

function CoaLibrary() {
  const [tab, setTab] = useState<Tab>('customer')
  const [masterRows, setMasterRows] = useState<LotCoaCertificateRow[]>([])
  const [customerRows, setCustomerRows] = useState<LotCoaCustomerCopyRow[]>([])
  const [skuInput, setSkuInput] = useState('')
  const [soInput, setSoInput] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      setLoading(true)
      const sku = skuInput.trim()
      const so = soInput.trim()
      const masterParams = sku ? { sku } : undefined
      const customerParams: { sku?: string; so?: string } = {}
      if (sku) customerParams.sku = sku
      if (so) customerParams.so = so

      const [masterData, customerData] = await Promise.all([
        getLotCoaCertificates(masterParams),
        getLotCoaCustomerCopies(Object.keys(customerParams).length ? customerParams : undefined),
      ])
      setMasterRows(Array.isArray(masterData) ? masterData : [])
      setCustomerRows(Array.isArray(customerData) ? customerData : [])
    } catch (e) {
      console.error(e)
      alert('Failed to load COA certificates')
      setMasterRows([])
      setCustomerRows([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="coa-library">
      <div className="coa-library__header">
        <h2>Certificates of analysis</h2>
        <p className="coa-library__intro">
          <strong>Master COAs</strong> store micro/QC results when a lot is fully released from hold (internal lot certificate).
          <strong> Customer COAs</strong> are generated when that lot is allocated on a sales order—they use the order’s
          customer and customer reference (PO) and the allocated quantity.
        </p>
        <div className="coa-library__tabs">
          <button
            type="button"
            className={tab === 'customer' ? 'coa-library__tab active' : 'coa-library__tab'}
            onClick={() => setTab('customer')}
          >
            Customer COAs (by allocation)
          </button>
          <button
            type="button"
            className={tab === 'master' ? 'coa-library__tab active' : 'coa-library__tab'}
            onClick={() => setTab('master')}
          >
            Master (by lot)
          </button>
        </div>
        <div className="coa-library__filters">
          <label>
            Filter by SKU
            <input
              type="text"
              value={skuInput}
              onChange={(e) => setSkuInput(e.target.value)}
              placeholder="e.g. D1307 (exact SKU)"
              onKeyDown={(e) => e.key === 'Enter' && void load()}
            />
          </label>
          <label>
            Sales order # <span className="coa-library__filter-hint">(customer tab)</span>
            <input
              type="text"
              value={soInput}
              onChange={(e) => setSoInput(e.target.value)}
              placeholder="e.g. 3250001"
              onKeyDown={(e) => e.key === 'Enter' && void load()}
            />
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="coa-library__loading">Loading…</div>
      ) : tab === 'master' ? (
        <div className="coa-library__table-wrap">
          <table className="coa-library__table">
            <thead>
              <tr>
                <th>Lot</th>
                <th>SKU</th>
                <th>Product</th>
                <th>Issued</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {masterRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="coa-library__empty">
                    No master certificates found. Release a finished-good lot from hold with COA/micro data.
                  </td>
                </tr>
              ) : (
                masterRows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.lot_number}</strong>
                    </td>
                    <td>{r.item_sku}</td>
                    <td>{r.item_name}</td>
                    <td>{r.issued_at ? formatAppDateTimeShort(r.issued_at) : '—'}</td>
                    <td>
                      {r.coa_pdf_url ? (
                        <a href={r.coa_pdf_url} target="_blank" rel="noopener noreferrer" className="coa-library__pdf-link">
                          Master PDF
                        </a>
                      ) : (
                        <span className="coa-library__pending">Pending</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="coa-library__table-wrap">
          <table className="coa-library__table">
            <thead>
              <tr>
                <th>SO</th>
                <th>Lot</th>
                <th>SKU</th>
                <th>Product</th>
                <th>Customer</th>
                <th>Customer ref / PO</th>
                <th>Qty (alloc)</th>
                <th>Created</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {customerRows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="coa-library__empty">
                    No customer COAs yet. Allocate a lot that has a master COA onto a sales order, or adjust filters.
                  </td>
                </tr>
              ) : (
                customerRows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.so_number}</strong>
                    </td>
                    <td>{r.lot_number}</td>
                    <td>{r.item_sku}</td>
                    <td>{r.item_name}</td>
                    <td>{r.customer_name || '—'}</td>
                    <td>{r.customer_po || '—'}</td>
                    <td>{r.quantity_snapshot}</td>
                    <td>{r.created_at ? formatAppDateTimeShort(r.created_at) : '—'}</td>
                    <td>
                      {r.coa_pdf_url ? (
                        <a href={r.coa_pdf_url} target="_blank" rel="noopener noreferrer" className="coa-library__pdf-link">
                          Open PDF
                        </a>
                      ) : (
                        <span className="coa-library__pending">Pending</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default CoaLibrary
