import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import Inventory from './pages/Inventory'
import './App.css'

function App() {
  return (
    <Router>
      <div className="App">
        <header className="app-header">
          <div className="header-content">
            <h1>WWI ERP System</h1>
            <nav className="main-nav">
              <Link to="/" className="nav-link">Home</Link>
              <Link to="/inventory/summary" className="nav-link">Inventory</Link>
            </nav>
          </div>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={
              <div className="welcome-page">
                <h2>Welcome to WWI ERP System</h2>
                <p>Manage your inventory, production, and orders from one place.</p>
                <Link to="/inventory/summary" className="btn btn-primary">Go to Inventory</Link>
              </div>
            } />
            <Route path="/inventory/*" element={<Inventory />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App

