import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'
import { useAuth } from './AuthContext'

/** Current preference key */
const STORAGE_KEY = 'erp_god_mode'
/** Migrated from former "backdated entry" toggle */
const LEGACY_STORAGE_KEY = 'erp_backdated_entry'

function readStored(): boolean {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v !== null) return v === '1' || v === 'true'
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
    return legacy === '1' || legacy === 'true'
  } catch {
    return false
  }
}

function persistStored(on: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

export interface GodModeContextValue {
  /** Staff/superuser only — only they can turn God mode on */
  canUseGodMode: boolean
  /** When on, date inputs are not clamped to today (any date allowed) */
  godModeOn: boolean
  setGodModeOn: (on: boolean) => void
  /** For date inputs: max date when God mode is off (typically today) */
  maxDateForEntry: string | undefined
  /** For date inputs: min date when God mode is off (typically today) */
  minDateForEntry: string | undefined
}

const GodModeContext = createContext<GodModeContextValue | null>(null)

export function GodModeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const canUseGodMode = Boolean(user?.is_staff || user?.is_superuser)
  const [godModeOn, setState] = useState(readStored)

  const setGodModeOn = useCallback((on: boolean) => {
    setState(on)
    persistStored(on)
  }, [])

  const today = useMemo(() => {
    const d = new Date()
    return (
      d.getFullYear() +
      '-' +
      String(d.getMonth() + 1).padStart(2, '0') +
      '-' +
      String(d.getDate()).padStart(2, '0')
    )
  }, [])

  const value: GodModeContextValue = useMemo(
    () => ({
      canUseGodMode,
      godModeOn,
      setGodModeOn,
      maxDateForEntry: godModeOn ? undefined : today,
      minDateForEntry: godModeOn ? undefined : today,
    }),
    [canUseGodMode, godModeOn, setGodModeOn, today]
  )

  return <GodModeContext.Provider value={value}>{children}</GodModeContext.Provider>
}

export function useGodMode() {
  const ctx = useContext(GodModeContext)
  if (!ctx) throw new Error('useGodMode must be used within GodModeProvider')
  return ctx
}
