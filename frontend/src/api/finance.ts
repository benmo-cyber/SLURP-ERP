import { api } from './client'
import { getItems } from './inventory'

// Re-export getItems for convenience
export { getItems }

// Customer Pricing API
export const getCustomerPricing = async () => {
  const response = await api.get('/customer-pricing/')
  return response.data.results || response.data
}

export const createCustomerPricing = async (data: any) => {
  const response = await api.post('/customer-pricing/', data)
  return response.data
}

/** Customer pricing history by product code(s) for margin/trend charts */
export const getCustomerPricingHistory = async (productCodes: string[]) => {
  const params = productCodes.map(code => `product_code=${encodeURIComponent(code)}`).join('&')
  const response = await api.get(`/customer-pricing/price_history/?${params}`)
  return response.data
}

// Vendor Pricing API
export const getVendorPricing = async () => {
  const response = await api.get('/vendor-pricing/')
  return response.data.results || response.data
}

export const createVendorPricing = async (data: any) => {
  const response = await api.post('/vendor-pricing/', data)
  return response.data
}

// Invoices API
export const getInvoices = async () => {
  const response = await api.get('/invoices/')
  return response.data.results || response.data
}

export const getInvoice = async (id: number) => {
  const response = await api.get(`/invoices/${id}/`)
  return response.data
}

export const createInvoice = async (data: any) => {
  const response = await api.post('/invoices/', data)
  return response.data
}

export const updateInvoice = async (id: number, data: any) => {
  const response = await api.put(`/invoices/${id}/`, data)
  return response.data
}

// Accounts API
export const getAccounts = async () => {
  const response = await api.get('/accounts/')
  return response.data.results || response.data
}

export const getAccount = async (id: number) => {
  const response = await api.get(`/accounts/${id}/`)
  return response.data
}

export const createAccount = async (data: any) => {
  const response = await api.post('/accounts/', data)
  return response.data
}

export const updateAccount = async (id: number, data: any) => {
  const response = await api.put(`/accounts/${id}/`, data)
  return response.data
}

// Journal Entries API
export const getJournalEntries = async (params?: { status?: string, start_date?: string, end_date?: string }) => {
  const response = await api.get('/journal-entries/', { params })
  return response.data.results || response.data
}

export const getJournalEntry = async (id: number) => {
  const response = await api.get(`/journal-entries/${id}/`)
  return response.data
}

export const createJournalEntry = async (data: any) => {
  const response = await api.post('/journal-entries/', data)
  return response.data
}

export const updateJournalEntry = async (id: number, data: any) => {
  const response = await api.put(`/journal-entries/${id}/`, data)
  return response.data
}

export const postJournalEntry = async (id: number) => {
  const response = await api.post(`/journal-entries/${id}/post/`)
  return response.data
}

// Financial Reports API
export const getTrialBalance = async (params?: { as_of_date?: string, fiscal_period_id?: number }) => {
  const response = await api.get('/financial-reports/trial-balance/', { params })
  return response.data
}

export const getBalanceSheet = async (params?: { as_of_date?: string, fiscal_period_id?: number }) => {
  const response = await api.get('/financial-reports/balance-sheet/', { params })
  return response.data
}

export const getIncomeStatement = async (params?: { start_date?: string, end_date?: string, fiscal_period_id?: number }) => {
  const response = await api.get('/financial-reports/income-statement/', { params })
  return response.data
}

export const getCashFlowStatement = async (params?: { start_date?: string, end_date?: string, fiscal_period_id?: number }) => {
  const response = await api.get('/financial-reports/cash-flow/', { params })
  return response.data
}

// Fiscal Periods API
export const getFiscalPeriods = async () => {
  const response = await api.get('/fiscal-periods/')
  return response.data.results || response.data
}

export const closeFiscalPeriod = async (id: number) => {
  const response = await api.post(`/fiscal-periods/${id}/close/`)
  return response.data
}

// Bank Reconciliations API
export const getBankReconciliations = async (params?: { account_id?: number }) => {
  const response = await api.get('/bank-reconciliations/', { params })
  return response.data.results || response.data
}

export const createBankReconciliation = async (data: { account: number; statement_date: string; statement_balance: number; notes?: string }) => {
  const response = await api.post('/bank-reconciliations/', data)
  return response.data
}

export const updateBankReconciliation = async (id: number, data: any) => {
  const response = await api.patch(`/bank-reconciliations/${id}/`, data)
  return response.data
}

// General Ledger API
export const getGeneralLedger = async (params?: { account_id?: number, start_date?: string, end_date?: string, fiscal_period_id?: number }) => {
  const response = await api.get('/general-ledger/', { params })
  return response.data.results || response.data
}

export const getAccountBalance = async (accountId: number, asOfDate: string) => {
  const response = await api.get('/general-ledger/account-balance/', { 
    params: { account_id: accountId, as_of_date: asOfDate }
  })
  return response.data
}

/** One vendor PO row for the AP workbench (issued+), with AP lines grouped by landed-cost category. */
export interface ApPoWorkqueueRow {
  purchase_order_id: number
  po_number: string
  vendor_name: string
  po_status: string
  order_date: string
  payment_workflow: 'awaiting_bills' | 'open' | 'partial' | 'paid' | 'overdue'
  /** From Quality → Vendor profile (e.g. Net 30) */
  vendor_payment_terms?: string | null
  /** Earliest due date among open-balance AP lines on this PO */
  next_open_due_date?: string | null
  total_open_balance: number
  ap_line_count: number
  material_entries: AccountsPayableLine[]
  freight_entries: AccountsPayableLine[]
  duty_tax_entries: AccountsPayableLine[]
}

export interface AccountsPayableLine {
  id: number
  vendor_name: string
  invoice_number: string | null
  invoice_date: string
  due_date: string
  original_amount: number
  amount_paid: number
  balance: number
  status: string
  days_aging: number
  aging_bucket: string
  po_number?: string | null
  purchase_order?: number | null
  freight_total?: number | null
  tariff_duties_paid?: number | null
  shipment_method?: string | null
  notes?: string | null
  cost_category?: string
}

export interface CreateApForPoPayload {
  purchase_order: number
  cost_category: '' | 'material' | 'freight' | 'duty_tax'
  original_amount: number
  invoice_number?: string | null
  invoice_date?: string
  due_date?: string
  vendor_name?: string | null
  freight_total?: number | null
  tariff_duties_paid?: number | null
  shipment_method?: string | null
  notes?: string | null
}

// Accounts Payable API
export const getAccountsPayable = async (params?: {
  status?: string
  vendor_name?: string
  due_date_from?: string
  due_date_to?: string
  standalone_only?: boolean | string
}) => {
  const { standalone_only, ...rest } = params || {}
  const response = await api.get('/accounts-payable/', {
    params: {
      ...rest,
      ...(standalone_only === true || standalone_only === 'true' ? { standalone_only: 'true' } : {}),
    },
  })
  return response.data.results || response.data
}

export const getApPoWorkqueue = async (params?: { vendor_name?: string; workflow?: string }) => {
  const response = await api.get('/accounts-payable/po-workqueue/', { params })
  return response.data as ApPoWorkqueueRow[]
}

export const createAccountsPayableForPo = async (data: CreateApForPoPayload) => {
  const response = await api.post('/accounts-payable/create-for-po/', data)
  return response.data as AccountsPayableLine
}

export const getAccountsPayableAging = async () => {
  const response = await api.get('/accounts-payable/aging/')
  return response.data
}

export const getAccountsPayableEntry = async (id: number) => {
  const response = await api.get(`/accounts-payable/${id}/`)
  return response.data
}

export const updateAccountsPayableEntry = async (id: number, data: any) => {
  const response = await api.patch(`/accounts-payable/${id}/`, data)
  return response.data
}

// Accounts Receivable API
export const getAccountsReceivable = async (params?: { status?: string, customer_name?: string, due_date_from?: string, due_date_to?: string }) => {
  const response = await api.get('/accounts-receivable/', { params })
  return response.data.results || response.data
}

export const getAccountsReceivableAging = async () => {
  const response = await api.get('/accounts-receivable/aging/')
  return response.data
}

export const getAccountsReceivableEntry = async (id: number) => {
  const response = await api.get(`/accounts-receivable/${id}/`)
  return response.data
}

export const updateAccountsReceivableEntry = async (id: number, data: any) => {
  const response = await api.put(`/accounts-receivable/${id}/`, data)
  return response.data
}

// Payments API
export const getPayments = async (params?: { payment_type?: string, date_from?: string, date_to?: string }) => {
  const response = await api.get('/payments/', { params })
  return response.data.results || response.data
}

export const getPayment = async (id: number) => {
  const response = await api.get(`/payments/${id}/`)
  return response.data
}

export const createPayment = async (data: any) => {
  const response = await api.post('/payments/', data)
  return response.data
}

export const updatePayment = async (id: number, data: any) => {
  const response = await api.put(`/payments/${id}/`, data)
  return response.data
}

// Dashboard Metrics API
export const getDashboardMetrics = async (params?: { period_type?: 'monthly' | 'quarterly', months_back?: number }) => {
  const response = await api.get('/financial-reports/dashboard-metrics/', { params })
  return response.data
}

// KPIs (performance metrics) API
export const getKpis = async (params?: { months_back?: number }) => {
  const response = await api.get('/financial-reports/kpis/', { params })
  return response.data
}

// Customer Forecasts API (for forecast vs actual)
export const getCustomerForecasts = async (params?: { customer_id?: number, forecast_period?: string }) => {
  const response = await api.get('/customer-forecasts/', { params })
  return response.data.results || response.data
}
