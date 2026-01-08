import { useState } from 'react'
import CreateSalesOrder from '../components/sales/CreateSalesOrder'
import './Sales.css'

function Sales() {
  const [showCreateSO, setShowCreateSO] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleCreateSOSuccess = () => {
    setShowCreateSO(false)
    setRefreshKey(prev => prev + 1)
  }

  return (
    <div className="sales-page">
      <div className="page-header">
        <h1>Sales</h1>
        <button onClick={() => setShowCreateSO(true)} className="btn btn-primary">
          Create Sales Order from Customer PO
        </button>
      </div>
      <div className="page-content">
        {showCreateSO && (
          <CreateSalesOrder
            onClose={() => setShowCreateSO(false)}
            onSuccess={handleCreateSOSuccess}
          />
        )}
      </div>
    </div>
  )
}

export default Sales
