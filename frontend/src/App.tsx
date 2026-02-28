import { useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Inventory from './pages/Inventory'
import Finance from './pages/Finance'
import Production from './pages/Production'
import Quality from './pages/Quality'
import Sales from './pages/Sales'
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

function App() {
  usePreventWheelOnNumberInputs()
  return (
    <Router>
      <div className="App">
        <header className="app-header">
          <div className="header-content">
            <div className="header-brand">
              <img src="/logo.png" alt="Wildwood Ingredients" className="header-logo" />
              <h1>SLURP</h1>
            </div>
            <Navigation />
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
      </div>
    </Router>
  )
}

export default App

