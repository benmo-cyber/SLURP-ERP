import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import * as authApi from '../api/auth'
import type { AuthUser, MeResponse } from '../api/auth'

interface AuthState {
  user: AuthUser | null
  loading: boolean
  error: string | null
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  })

  const refreshUser = useCallback(async () => {
    try {
      const data = await authApi.me()
      if (data.authenticated && data.username && data.role != null && data.id != null) {
        setState({
          user: {
            id: data.id,
            username: data.username,
            email: data.email || '',
            role: data.role,
            is_staff: data.is_staff,
            is_superuser: data.is_superuser,
          },
          loading: false,
          error: null,
        })
      } else {
        setState({ user: null, loading: false, error: null })
      }
    } catch (err: any) {
      const isNetworkError = err?.code === 'ERR_NETWORK' || !err?.response
      if (isNetworkError) {
        // Backend unreachable: don't clear user so we don't "log them out"
        setState((prev) => ({
          user: prev.user,
          loading: false,
          error: 'Cannot reach server. Start the backend (e.g. python manage.py runserver on port 8000) and refresh.',
        }))
      } else {
        setState({ user: null, loading: false, error: null })
      }
    }
  }, [])

  useEffect(() => {
    authApi.getCsrf().catch(() => {})
    refreshUser()
  }, [refreshUser])

  useEffect(() => {
    const handler = () => refreshUser()
    window.addEventListener('auth:unauthorized', handler)
    return () => window.removeEventListener('auth:unauthorized', handler)
  }, [refreshUser])

  const login = useCallback(async (username: string, password: string) => {
    setState((s) => ({ ...s, error: null }))
    try {
      const user = await authApi.login(username, password)
      setState({ user, loading: false, error: null })
    } catch (err: any) {
      const data = err.response?.data
      let message = (typeof data?.error === 'string' && data.error) ||
        (typeof data?.detail === 'string' && data.detail) ||
        (Array.isArray(data?.detail) && data.detail[0]) ||
        null
      if (!message) {
        if (err.code === 'ERR_NETWORK' || !err.response) {
          message = 'Cannot reach server. Check that the backend is running (e.g. port 8000) and try again.'
        } else {
          message = `Login failed${err.response?.status ? ` (${err.response.status})` : ''}. Try again or check your credentials.`
        }
      }
      setState((s) => ({ ...s, loading: false, error: message }))
      throw new Error(message)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setState({ user: null, loading: false, error: null })
    }
  }, [])

  const clearError = useCallback(() => {
    setState((s) => ({ ...s, error: null }))
  }, [])

  const value: AuthContextValue = {
    ...state,
    login,
    logout,
    refreshUser,
    clearError,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
