import { useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth, AuthProvider } from './context/AuthContext'
import { BackdatedEntryProvider, useBackdatedEntry } from './context/BackdatedEntryContext'
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

function HeaderBackdatedToggle() {
  const { canUseBackdatedEntry, backdatedEntryOn, setBackdatedEntryOn } = useBackdatedEntry()
  if (!canUseBackdatedEntry) return null
  return (
    <label className="header-backdated-toggle">
      <input
        type="checkbox"
        checked={backdatedEntryOn}
        onChange={(e) => setBackdatedEntryOn(e.target.checked)}
        title="Allow entering past dates (e.g. received, production, ship)"
      />
      <span>Backdated entry</span>
    </label>
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
      <HeaderBackdatedToggle />
      <span className="header-username">{user.username}</span>
      <span className="header-role">({user.role})</span>
      <button type="button" className="header-logout" onClick={handleLogout}>Sign out</button>
    </div>
  )
}

function App() {
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
                <BackdatedEntryProvider>
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
                </BackdatedEntryProvider>
              </ProtectedRoute>
            } />
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  )
}

export default App

