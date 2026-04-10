/**
 * Service vendor type options. Keep in sync with backend Vendor.SERVICE_VENDOR_TYPE_CHOICES.
 * To add a new type: add it here and in backend_django/erp_core/models.py Vendor.SERVICE_VENDOR_TYPE_CHOICES.
 */
export const SERVICE_VENDOR_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '—' },
  { value: 'customs_broker', label: 'Customs Broker' },
  { value: 'freight_forwarder', label: 'Freight Forwarder' },
]

export function getServiceVendorTypeLabel(value: string | null | undefined): string {
  if (value == null || value === '') return '—'
  const option = SERVICE_VENDOR_TYPE_OPTIONS.find((o) => o.value === value)
  return option ? option.label : value
}
