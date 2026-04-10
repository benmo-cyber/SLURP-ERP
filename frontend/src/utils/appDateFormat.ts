/**
 * US Central with DST (same as Django `TIME_ZONE` / `BUSINESS_TIME_ZONE`): IANA `America/Chicago`.
 * Not a fixed offset — CST in winter, CDT in summer. Keeps UI aligned with Missouri business time.
 */
export const APP_TIME_ZONE = 'America/Chicago'

function toValidDate(input: string | Date | null | undefined): Date | null {
  if (input == null || input === '') return null
  const d = input instanceof Date ? input : new Date(input)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatAppDate(input: string | Date | null | undefined): string {
  const d = toValidDate(input)
  if (!d) return ''
  return d.toLocaleDateString('en-US', { timeZone: APP_TIME_ZONE })
}

export function formatAppDateMedium(input: string | Date | null | undefined): string {
  const d = toValidDate(input)
  if (!d) return ''
  return d.toLocaleDateString('en-US', {
    timeZone: APP_TIME_ZONE,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatAppDateTime(input: string | Date | null | undefined): string {
  const d = toValidDate(input)
  if (!d) return ''
  return d.toLocaleString('en-US', {
    timeZone: APP_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatAppDateTimeShort(input: string | Date | null | undefined): string {
  const d = toValidDate(input)
  if (!d) return ''
  return d.toLocaleString('en-US', {
    timeZone: APP_TIME_ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

/**
 * API date-only fields (YYYY-MM-DD). Avoids `new Date('YYYY-MM-DD')` UTC-midnight off-by-one in US time.
 */
export function formatAppDateFromYmd(ymd: string | null | undefined): string {
  if (!ymd) return 'N/A'
  const m = ymd.trim().match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return formatAppDate(ymd) || 'N/A'
  const y = parseInt(m[1], 10)
  const mo = parseInt(m[2], 10) - 1
  const d = parseInt(m[3], 10)
  const noonUtc = new Date(Date.UTC(y, mo, d, 12, 0, 0))
  return noonUtc.toLocaleDateString('en-US', { timeZone: APP_TIME_ZONE })
}
