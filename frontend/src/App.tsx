import { useEffect, useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth, AuthProvider } from './context/AuthContext'
import { GodModeProvider, useGodMode } from './context/GodModeContext'
import ProtectedRoute from './components/ProtectedRoute'
import Inventory from './pages/Inventory'
import Finance from './pages/Finance'
import Production from './pages/Production'
import Quality from './pages/Quality'
import Sales from './pages/Sales'
import Login from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import './App.css'
import { importPrivateSampleXml } from './api/sampleImport'

/** Prevent mouse wheel from changing number inputs when hovering (stops accidental scroll-to-increment). */
function usePreventWheelOnNumberInputs() {
  useEffect(() => {
    const handler = (e: WheelEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'number') {
        e.preventDefault()
      }
    }
    document.addEventListener('wheel', handler, { passive: false, capture: true })
    return () => document.removeEventListener('wheel', handler, { capture: true })
  }, [])
}

function Navigation() {
  const location = useLocation()
  const currentPath = location.pathname.split('/')[1] || 'inventory'

  const tabs = [
    { id: 'inventory', label: 'Inventory', path: '/inventory' },
    { id: 'finance', label: 'Finance', path: '/finance' },
    { id: 'production', label: 'Production', path: '/production' },
    { id: 'quality', label: 'Quality', path: '/quality' },
    { id: 'sales', label: 'Sales', path: '/sales' },
  ]

  return (
    <nav className="main-nav">
      {tabs.map((tab) => (
        <Link
          key={tab.id}
          to={tab.path}
          className={`nav-link ${currentPath === tab.id ? 'active' : ''}`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  )
}

function HeaderGodModeToggle() {
  const { canUseGodMode, godModeOn, setGodModeOn } = useGodMode()
  if (!canUseGodMode) return null
  return (
    <label className="header-god-mode-toggle">
      <input
        type="checkbox"
        checked={godModeOn}
        onChange={(e) => setGodModeOn(e.target.checked)}
        title="God mode: set any date on forms and flows (staff only)"
      />
      <span>God mode</span>
    </label>
  )
}

function HeaderStaffSampleImport() {
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  if (!user?.is_staff) return null
  const run = async () => {
    setMsg(null)
    setBusy(true)
    try {
      const data = await importPrivateSampleXml() as {
        ok?: boolean
        message?: string
        error?: string
        totals?: Record<string, number>
        files?: unknown[]
      }
      if (data.message) {
        setMsg(data.message)
      } else if (data.error) {
        setMsg(String(data.error))
      } else if (data.totals) {
        setMsg(`Imported: ${JSON.stringify(data.totals)}`)
      } else {
        setMsg('Import finished.')
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      setMsg(err.response?.data?.error || (e instanceof Error ? e.message : 'Import failed'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="header-sample-import">
      <button
        type="button"
        className="header-sample-import-btn"
        disabled={busy}
        onClick={run}
        title="Loads all .xml files from server folder data/private_sample_data/"
      >
        {busy ? 'Importing…' : 'Import sample XML'}
      </button>
      {msg ? <span className="header-sample-import-msg" role="status">{msg}</span> : null}
    </div>
  )
}

function HeaderUser() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  if (!user) return null
  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }
  return (
    <div className="header-user">
      <HeaderGodModeToggle />
      <HeaderStaffSampleImport />
      <span className="header-username">{user.username}</span>
      <span className="header-role">({user.role})</span>
      <button type="button" className="header-logout" onClick={handleLogout}>Sign out</button>
    </div>
  )
}

function ConnectionBanner() {
  const { user, error, clearError } = useAuth()
  if (!user || !error || !error.includes('Cannot reach server')) return null
  return (
    <div className="connection-banner" role="alert">
      <span>{error}</span>
      <button type="button" className="connection-banner-dismiss" onClick={clearError} aria-label="Dismiss">×</button>
    </div>
  )
}

export default function App() {
  usePreventWheelOnNumberInputs()
  return (
    <Router>
      <AuthProvider>
        <div className="App">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/*" element={
              <ProtectedRoute>
                <GodModeProvider>
                  <>
                    <header className="app-header">
                    <div className="header-content">
                      <div className="header-brand">
                        <img src="/logo.png" alt="Wildwood Ingredients" className="header-logo" />
                        <h1>SLURP</h1>
                      </div>
                      <Navigation />
                      <HeaderUser />
                    </div>
                  </header>
                  <ConnectionBanner />
                  <main className="app-main">
                    <Routes>
                      <Route path="/" element={<Inventory />} />
                      <Route path="/inventory/*" element={<Inventory />} />
                      <Route path="/finance/*" element={<Finance />} />
                      <Route path="/production/*" element={<Production />} />
                      <Route path="/quality/*" element={<Quality />} />
                      <Route path="/sales/*" element={<Sales />} />
                    </Routes>
                  </main>
                  </>
                </GodModeProvider>
              </ProtectedRoute>
            } />
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  )
}

