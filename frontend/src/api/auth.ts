import { api, fetchAndStoreCsrf } from './client'

export type Role = 'viewer' | 'operator' | 'manager' | 'admin'

export interface AuthUser {
  id: number
  username: string
  email: string
  role: Role
  is_staff?: boolean
  is_superuser?: boolean
}

export interface MeResponse {
  authenticated: boolean
  username?: string
  email?: string
  role?: Role
  id?: number
  is_staff?: boolean
  is_superuser?: boolean
}

/** Ensure we have a CSRF token (call once before login or on app init). */
export async function getCsrf(): Promise<string> {
  return fetchAndStoreCsrf()
}

export async function login(username: string, password: string): Promise<AuthUser> {
  await getCsrf()
  const r = await api.post<AuthUser>('/auth/login/', { username, password })
  await getCsrf()
  return r.data
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout/')
  await getCsrf()
}

export async function me(): Promise<MeResponse> {
  const r = await api.get<MeResponse>('/auth/me/')
  return r.data
}

export async function passwordResetRequest(email: string): Promise<{ message?: string; error?: string }> {
  await getCsrf()
  const r = await api.post<{ message?: string; error?: string }>('/auth/password-reset/', { email })
  return r.data
}

export async function passwordResetConfirm(uid: string, token: string, newPassword: string): Promise<{ message?: string; error?: string }> {
  await getCsrf()
  const r = await api.post<{ message?: string; error?: string }>(
    `/auth/password-reset-confirm/${uid}/${token}/`,
    { new_password: newPassword }
  )
  return r.data
}
