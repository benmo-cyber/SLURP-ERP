/**
 * Shared API client: sends cookies (session) and CSRF token for mutating requests.
 */
import axios from 'axios'

export const API_BASE_URL = 'http://localhost:8000/api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

let csrfToken: string | null = null

export function setCsrfToken(token: string) {
  csrfToken = token
}

export function getCsrfToken(): string | null {
  return csrfToken
}

/** GET /auth/csrf/ and store token (used by auth helpers and CSRF retry). */
export async function fetchAndStoreCsrf(): Promise<string> {
  const r = await api.get<{ csrfToken: string }>('/auth/csrf/')
  const token = r.data.csrfToken
  setCsrfToken(token)
  return token
}

api.interceptors.request.use((config) => {
  if (csrfToken && ['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase())) {
    config.headers['X-CSRFToken'] = csrfToken
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as typeof error.config & { _csrfRetry?: boolean }
    const status = error.response?.status
    const raw = error.response?.data as { detail?: string } | string | undefined
    const detail =
      typeof raw === 'string'
        ? raw
        : typeof raw?.detail === 'string'
          ? raw.detail
          : ''
    const isCsrf403 =
      status === 403 &&
      config &&
      !config._csrfRetry &&
      (detail.includes('CSRF') || detail.toLowerCase().includes('csrf'))

    if (isCsrf403) {
      config._csrfRetry = true
      try {
        await fetchAndStoreCsrf()
        return api.request(config)
      } catch {
        // fall through to reject
      }
    }

    if (status === 401 && !config?.url?.includes('/auth/')) {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    return Promise.reject(error)
  }
)
