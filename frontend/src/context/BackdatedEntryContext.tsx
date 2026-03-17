import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'
import { useAuth } from './AuthContext'

const STORAGE_KEY = 'erp_backdated_entry'

function readStored(): boolean {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === '1' || v === 'true'
  } catch {
    return false
  }
}

interface BackdatedEntryContextValue {
  /** Whether the user is allowed to enable backdated entry (staff or superuser). */
  canUseBackdatedEntry: boolean
  /** Whether backdated entry mode is currently on (date inputs allow any date). */
  backdatedEntryOn: boolean
  setBackdatedEntryOn: (on: boolean) => void
  /** For date inputs: use as max when backdated is off (e.g. received date, ship date). */
  maxDateForEntry: string | undefined
  /** For date inputs that default to today-or-future: use as min when backdated is off (e.g. production date). */
  minDateForEntry: string | undefined
}

const BackdatedEntryContext = createContext<BackdatedEntryContextValue | null>(null)

export function BackdatedEntryProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const canUseBackdatedEntry = Boolean(user?.is_staff || user?.is_superuser)
  const [backdatedEntryOn, setState] = useState(readStored)

  const setBackdatedEntryOn = useCallback((on: boolean) => {
    setState(on)
    try {
      localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
    } catch {
      // ignore
    }
  }, [])

  const today = useMemo(() => {
    const d = new Date()
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
  }, [])

  const value: BackdatedEntryContextValue = useMemo(
    () => ({
      canUseBackdatedEntry,
      backdatedEntryOn,
      setBackdatedEntryOn,
      maxDateForEntry: backdatedEntryOn ? undefined : today,
      minDateForEntry: backdatedEntryOn ? undefined : today,
    }),
    [canUseBackdatedEntry, backdatedEntryOn, setBackdatedEntryOn, today]
  )

  return (
    <BackdatedEntryContext.Provider value={value}>
      {children}
    </BackdatedEntryContext.Provider>
  )
}

export function useBackdatedEntry() {
  const ctx = useContext(BackdatedEntryContext)
  if (!ctx) throw new Error('useBackdatedEntry must be used within BackdatedEntryProvider')
  return ctx
}
